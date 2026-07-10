FROM python:3.11-slim

# Install system dependencies required for database compilation layers
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Runs the gateway with 4 high-concurrency background processing workers
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "src.server.gateway_server:app"]
