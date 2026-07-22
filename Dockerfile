FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir \
    "python-telegram-bot[job-queue]==21.3" \
    requests==2.32.3 \
    beautifulsoup4==4.12.3

CMD ["python", "main.py"]
