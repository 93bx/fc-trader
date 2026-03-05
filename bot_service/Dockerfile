FROM budtmo/docker-android:emulator_13.0
USER root
RUN apt-get update -qq && apt-get install -y -qq \
    python3.11 python3.11-pip \
    tesseract-ocr tesseract-ocr-eng \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    sqlite3 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt
COPY . /app/
RUN mkdir -p /app/logs /app/apk /app/data
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["python3.11", "main.py"]
