from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from math import ceil
from typing import Callable

from google.protobuf.duration_pb2 import Duration

from fulcrum_grpc_api.envoy.service.ratelimit.v3 import rls_pb2, rls_pb2_grpc
from fulcrum_grpc_api.envoy.type.v3 import ratelimit_unit_pb2


SECONDS_BY_UNIT = {
    ratelimit_unit_pb2.SECOND: 1,
    ratelimit_unit_pb2.MINUTE: 60,
    ratelimit_unit_pb2.HOUR: 60 * 60,
    ratelimit_unit_pb2.DAY: 24 * 60 * 60,
    ratelimit_unit_pb2.WEEK: 7 * 24 * 60 * 60,
    ratelimit_unit_pb2.MONTH: 30 * 24 * 60 * 60,
    ratelimit_unit_pb2.YEAR: 365 * 24 * 60 * 60,
}

RLS_UNIT_BY_LIMIT_UNIT = {
    ratelimit_unit_pb2.SECOND: rls_pb2.RateLimitResponse.RateLimit.SECOND,
    ratelimit_unit_pb2.MINUTE: rls_pb2.RateLimitResponse.RateLimit.MINUTE,
    ratelimit_unit_pb2.HOUR: rls_pb2.RateLimitResponse.RateLimit.HOUR,
    ratelimit_unit_pb2.DAY: rls_pb2.RateLimitResponse.RateLimit.DAY,
    ratelimit_unit_pb2.WEEK: rls_pb2.RateLimitResponse.RateLimit.WEEK,
    ratelimit_unit_pb2.MONTH: rls_pb2.RateLimitResponse.RateLimit.MONTH,
    ratelimit_unit_pb2.YEAR: rls_pb2.RateLimitResponse.RateLimit.YEAR,
}


@dataclass(frozen=True)
class Limit:
    name: str
    requests_per_unit: int
    unit: int


@dataclass
class Bucket:
    limit: Limit
    tokens: float
    updated_at: float


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: Limit
    remaining: int
    reset_after_seconds: float


class TokenBucketRateLimiter:
    """Thread-safe in-memory token bucket storage."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[str, Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: Limit, hits: int) -> Decision:
        now = self._clock()
        unit_seconds = SECONDS_BY_UNIT.get(
            limit.unit,
            SECONDS_BY_UNIT[ratelimit_unit_pb2.MINUTE],
        )
        capacity = float(max(limit.requests_per_unit, 1))
        refill_per_second = capacity / unit_seconds

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or bucket.limit != limit:
                bucket = Bucket(limit=limit, tokens=capacity, updated_at=now)
                self._buckets[key] = bucket

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_per_second)
            bucket.updated_at = now

            if hits < 0:
                bucket.tokens = min(capacity, bucket.tokens + abs(hits))
                return Decision(True, limit, int(bucket.tokens), 0.0)

            if bucket.tokens >= hits:
                bucket.tokens -= hits
                return Decision(True, limit, int(bucket.tokens), 0.0)

            missing_tokens = hits - bucket.tokens
            reset_after = missing_tokens / refill_per_second
            return Decision(False, limit, int(bucket.tokens), reset_after)


def default_limit_from_env() -> Limit:
    requests_per_unit = int(os.getenv("FULCRUM_RATE_LIMIT_REQUESTS_PER_UNIT", "100"))
    unit_name = os.getenv("FULCRUM_RATE_LIMIT_UNIT", "MINUTE").upper()
    unit = getattr(ratelimit_unit_pb2, unit_name, ratelimit_unit_pb2.MINUTE)
    return Limit("default", requests_per_unit, unit)


class RateLimitServicer(rls_pb2_grpc.RateLimitServiceServicer):
    """Envoy rate limit gRPC servicer backed by in-memory token buckets."""

    def __init__(
        self,
        limiter: TokenBucketRateLimiter | None = None,
        default_limit: Limit | None = None,
    ) -> None:
        self._limiter = limiter or TokenBucketRateLimiter()
        self._default_limit = default_limit or default_limit_from_env()

    def ShouldRateLimit(self, request, context):
        statuses = []

        for descriptor in request.descriptors:
            limit = self._limit_for_descriptor(descriptor)
            key = self._key_for_descriptor(request.domain, descriptor)
            hits = self._hits_for_descriptor(request.hits_addend, descriptor)
            decision = self._limiter.check(key, limit, hits)
            statuses.append(self._status_for_decision(decision))

        if not statuses:
            limit = self._default_limit
            hits = request.hits_addend or 1
            decision = self._limiter.check(
                f"{request.domain or 'default'}:global",
                limit,
                hits,
            )
            statuses.append(self._status_for_decision(decision))

        overall_code = rls_pb2.RateLimitResponse.OK
        if any(status.code == rls_pb2.RateLimitResponse.OVER_LIMIT for status in statuses):
            overall_code = rls_pb2.RateLimitResponse.OVER_LIMIT

        return rls_pb2.RateLimitResponse(
            overall_code=overall_code,
            statuses=statuses,
        )

    def _limit_for_descriptor(self, descriptor) -> Limit:
        if descriptor.HasField("limit") and descriptor.limit.requests_per_unit > 0:
            unit = descriptor.limit.unit or self._default_limit.unit
            return Limit("descriptor", descriptor.limit.requests_per_unit, unit)
        return self._default_limit

    def _hits_for_descriptor(self, request_hits_addend: int, descriptor) -> int:
        if descriptor.HasField("hits_addend"):
            hits = int(descriptor.hits_addend.value)
        else:
            hits = int(request_hits_addend or 1)

        if descriptor.is_negative_hits:
            return -hits
        return max(hits, 1)

    def _key_for_descriptor(self, domain: str, descriptor) -> str:
        parts = [domain or "default"]
        entries = sorted(
            (entry.key or "unknown", entry.value or "")
            for entry in descriptor.entries
        )
        if not entries:
            parts.append("global")
        else:
            parts.extend(f"{key}={value}" for key, value in entries)
        return "|".join(parts)

    def _status_for_decision(self, decision: Decision):
        return rls_pb2.RateLimitResponse.DescriptorStatus(
            code=(
                rls_pb2.RateLimitResponse.OK
                if decision.allowed
                else rls_pb2.RateLimitResponse.OVER_LIMIT
            ),
            current_limit=rls_pb2.RateLimitResponse.RateLimit(
                name=decision.limit.name,
                requests_per_unit=decision.limit.requests_per_unit,
                unit=RLS_UNIT_BY_LIMIT_UNIT.get(
                    decision.limit.unit,
                    rls_pb2.RateLimitResponse.RateLimit.MINUTE,
                ),
            ),
            limit_remaining=decision.remaining,
            duration_until_reset=self._duration(decision.reset_after_seconds),
        )

    def _duration(self, seconds: float) -> Duration:
        duration = Duration()
        duration.FromSeconds(ceil(seconds))
        return duration
