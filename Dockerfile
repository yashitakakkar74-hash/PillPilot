FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
# one OCR thread: much faster on small shared servers such as Render's free plan
ENV OMP_THREAD_LIMIT=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
# Render sets PORT; locally it falls back to 5000
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 120 app:app"]
