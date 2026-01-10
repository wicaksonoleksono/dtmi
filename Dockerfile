FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir hypercorn

# Copy application code
COPY . .

EXPOSE ${APP_PORT}

CMD hypercorn ${APP_MODULE} --bind 0.0.0.0:${APP_PORT} --workers ${WORKERS}
