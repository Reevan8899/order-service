FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 \
    ORDER_DB_PATH=/data/orders.sqlite3
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && install -d -o 10001 -g 10001 /data
COPY app ./app
USER 10001:10001
EXPOSE 5002
CMD ["python", "-m", "app.main"]
