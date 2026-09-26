FROM python:3.11-slim

WORKDIR /app

# Hindari pembuatan file .pyc dan aktifkan log streaming
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install dependency terlebih dahulu agar memanfaatkan cache layer Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin source code aplikasi dan dokumen knowledge base
COPY app/ ./app/
COPY data/ ./data/

EXPOSE 8000

# Jalankan server uvicorn (mendukung environment PORT dinamis dari platform cloud)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
