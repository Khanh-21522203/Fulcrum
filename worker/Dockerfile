FROM python:3.12-slim
WORKDIR /app
COPY shared/ /shared
COPY providers/local/ /providers/local
RUN pip install --no-cache-dir /shared
RUN pip install --no-cache-dir /providers/local
COPY worker/ /app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "worker.main"]
