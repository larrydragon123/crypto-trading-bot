FROM python:3.11-slim

WORKDIR /app

COPY crypto_bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crypto_bot/ /app/crypto_bot/

RUN mkdir -p /app/logs

WORKDIR /app
CMD ["python", "-m", "crypto_bot.main"]
