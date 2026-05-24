FROM python:3.12-slim
WORKDIR /app
COPY rate-limit-sidecar/ /app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "rate_limit_sidecar.main"]
