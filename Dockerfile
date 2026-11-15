# Alternatív futtatás Dockerrel (arm64 / Raspberry Pi 4-5 is)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
ENV DATA_DIR=/data PORT=8080
VOLUME ["/data"]
EXPOSE 8080
CMD ["python", "-m", "app.main"]
