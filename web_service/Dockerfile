FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates fonts-liberation fonts-noto-color-emoji \
    libglib2.0-0 libnss3 libfontconfig1 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libx11-6 libxext6 libxrender1 libxtst6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium
RUN python -m playwright install-deps chromium
COPY . /app/
RUN mkdir -p /app/data/browser_profile

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/../bot_service:/app/../shared

CMD ["python3", "main.py"]
