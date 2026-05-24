FROM python:3.12-slim
WORKDIR /app
COPY shared/ /shared
RUN pip install --no-cache-dir /shared
COPY control-plane/ /app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "control_plane.main"]
