FROM python:3.11-slim

WORKDIR /app

# Dependencias de compilación para paquetes nativos si se requieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

ENV PYTHONPATH=/app/backend/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "python -m db.migrate && uvicorn main:app --app-dir /app/backend/src --host 0.0.0.0 --port 8000"]
