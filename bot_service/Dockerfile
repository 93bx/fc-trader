FROM budtmo/docker-android:emulator_13.0
USER root
RUN apt-get update -qq && apt-get install -y -qq software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update -qq \
    && apt-get install -y -qq \
        python3.11 python3.11-venv python3.11-distutils \
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
ENTRYPOINT ["python3.11", "main.py"]
CMD []
