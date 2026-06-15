# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for compilation if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure dependencies are explicitly installed
RUN pip install --no-cache-dir fastapi uvicorn pydantic pypdf python-multipart langchain-groq python-dotenv requests

# Copy backend source code and dataset
COPY backend/ ./backend/
COPY medicine_dataset.csv .

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Command to run uvicorn server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
