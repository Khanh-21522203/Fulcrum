FROM python:3.12-slim
WORKDIR /app
COPY grpc-api/ /grpc-api
RUN pip install --no-cache-dir /grpc-api
COPY rate-limit-sidecar/ /app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "rate_limit_sidecar.main"]
