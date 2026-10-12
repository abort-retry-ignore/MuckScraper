FROM python:3.12-slim

WORKDIR /app

COPY feed_proxy.py .

EXPOSE 8080

CMD ["python", "-u", "feed_proxy.py"]
