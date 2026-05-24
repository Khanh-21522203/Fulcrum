FROM python:3.12-slim
WORKDIR /app
COPY auth-sidecar/ /app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "auth_sidecar.main"]
