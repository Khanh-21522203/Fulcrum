import unittest
from concurrent import futures

import grpc
from google.protobuf.wrappers_pb2 import UInt64Value

from fulcrum_grpc_api.envoy.service.ratelimit.v3 import rls_pb2
from fulcrum_grpc_api.envoy.service.ratelimit.v3 import rls_pb2_grpc
from rate_limit_sidecar.service import (
    Limit,
    RateLimitServicer,
    RateLimitUnit,
    TokenBucketRateLimiter,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def descriptor(*entries, limit=None, hits=None, is_negative_hits=False):
    message = rls_pb2.RateLimitDescriptor(
        entries=[
            rls_pb2.RateLimitDescriptor.Entry(key=key, value=value)
            for key, value in entries
        ],
        is_negative_hits=is_negative_hits,
    )
    if limit is not None:
        requests_per_unit, unit = limit
        message.limit.requests_per_unit = requests_per_unit
        message.limit.unit = unit
    if hits is not None:
        message.hits_addend.CopyFrom(UInt64Value(value=hits))
    return message


def request(*descriptors, hits_addend=0):
    return rls_pb2.RateLimitRequest(
        domain="fulcrum",
        descriptors=list(descriptors),
        hits_addend=hits_addend,
    )


def service(clock, default_limit=None):
    return RateLimitServicer(
        limiter=TokenBucketRateLimiter(clock=clock),
        default_limit=default_limit
        or Limit("default", 2, RateLimitUnit.MINUTE),
    )


class RateLimitServicerTest(unittest.TestCase):
    def test_allows_until_bucket_is_empty(self):
        clock = FakeClock()
        servicer = service(clock)
        check = request(descriptor(("service_id", "broker")))

        first = servicer.ShouldRateLimit(check, None)
        second = servicer.ShouldRateLimit(check, None)
        third = servicer.ShouldRateLimit(check, None)

        self.assertEqual(first.overall_code, rls_pb2.RateLimitResponse.OK)
        self.assertEqual(second.overall_code, rls_pb2.RateLimitResponse.OK)
        self.assertEqual(third.overall_code, rls_pb2.RateLimitResponse.OVER_LIMIT)
        self.assertEqual(third.statuses[0].limit_remaining, 0)

    def test_refills_tokens_over_time(self):
        clock = FakeClock()
        servicer = service(clock)
        check = request(descriptor(("service_id", "broker")))

        servicer.ShouldRateLimit(check, None)
        servicer.ShouldRateLimit(check, None)
        clock.advance(30)

        response = servicer.ShouldRateLimit(check, None)

        self.assertEqual(response.overall_code, rls_pb2.RateLimitResponse.OK)

    def test_uses_descriptor_limit_override(self):
        clock = FakeClock()
        servicer = service(
            clock,
            default_limit=Limit("default", 100, RateLimitUnit.MINUTE),
        )
        check = request(
            descriptor(
                ("service_id", "broker"),
                limit=(1, RateLimitUnit.MINUTE),
            )
        )

        first = servicer.ShouldRateLimit(check, None)
        second = servicer.ShouldRateLimit(check, None)

        self.assertEqual(first.overall_code, rls_pb2.RateLimitResponse.OK)
        self.assertEqual(second.overall_code, rls_pb2.RateLimitResponse.OVER_LIMIT)
        self.assertEqual(second.statuses[0].current_limit.requests_per_unit, 1)

    def test_honors_hits_addend(self):
        clock = FakeClock()
        servicer = service(
            clock,
            default_limit=Limit("default", 3, RateLimitUnit.MINUTE),
        )
        check = request(descriptor(("service_id", "broker"), hits=2))

        first = servicer.ShouldRateLimit(check, None)
        second = servicer.ShouldRateLimit(check, None)

        self.assertEqual(first.overall_code, rls_pb2.RateLimitResponse.OK)
        self.assertEqual(first.statuses[0].limit_remaining, 1)
        self.assertEqual(second.overall_code, rls_pb2.RateLimitResponse.OVER_LIMIT)
        self.assertGreater(second.statuses[0].duration_until_reset.seconds, 0)

    def test_descriptors_have_separate_buckets(self):
        clock = FakeClock()
        servicer = service(clock)

        broker = request(descriptor(("service_id", "broker")))
        worker = request(descriptor(("service_id", "worker")))

        servicer.ShouldRateLimit(broker, None)
        servicer.ShouldRateLimit(broker, None)
        worker_response = servicer.ShouldRateLimit(worker, None)

        self.assertEqual(worker_response.overall_code, rls_pb2.RateLimitResponse.OK)
        self.assertEqual(worker_response.statuses[0].limit_remaining, 1)

    def test_grpc_service_returns_rate_limit_response(self):
        clock = FakeClock()
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        rls_pb2_grpc.add_RateLimitServiceServicer_to_server(service(clock), server)
        port = server.add_insecure_port("[::]:0")
        server.start()
        self.addCleanup(server.stop, 0)

        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = rls_pb2_grpc.RateLimitServiceStub(channel)
            response = stub.ShouldRateLimit(
                request(descriptor(("service_id", "broker"))),
                timeout=2,
            )

        self.assertEqual(response.overall_code, rls_pb2.RateLimitResponse.OK)


if __name__ == "__main__":
    unittest.main()
