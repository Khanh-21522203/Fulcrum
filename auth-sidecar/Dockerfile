FROM python:3.12-slim
WORKDIR /app
COPY grpc-api/ /app/grpc-api
COPY auth-sidecar/ /app/auth-sidecar
RUN pip install --no-cache-dir /app/grpc-api /app/auth-sidecar
CMD ["python", "-m", "auth_sidecar.main"]
