FROM python:3.12-slim
WORKDIR /app
COPY shared/ /shared
COPY grpc-api/ /grpc-api
COPY providers/local/ /providers/local
RUN pip install --no-cache-dir /shared
RUN pip install --no-cache-dir /grpc-api
RUN pip install --no-cache-dir /providers/local
COPY control-plane/ /app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "control_plane.main"]
