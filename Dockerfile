FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir python-telegram-bot==21.3
CMD ["python", "main.py"]
