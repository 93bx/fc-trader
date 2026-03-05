FROM python:3.11-slim
RUN apt-get update -qq && apt-get install -y -qq sqlite3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
RUN mkdir -p /app/data
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["python3", "main.py"]
