FROM python:3.11-slim

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set default port for Cloud Run
ENV PORT=8080
EXPOSE 8080

# Run uvicorn on port $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
