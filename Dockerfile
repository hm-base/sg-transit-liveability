# Dockerfile
# ============
# Builds the SG Transit Liveability pipeline container.
# Runs: FastAPI + ingestion workers + batch scheduler

FROM python:3.11-slim

# System dependencies for GeoPandas
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir uv && \
    uv pip install --system -r requirements.txt

# Copy source code
COPY . .

# Create data directory
RUN mkdir -p data/models

# Expose FastAPI port
EXPOSE 8000

# Environment variables (override at runtime)
ENV LTA_API_KEY=""
ENV ONEMAP_TOKEN=""
ENV PYTHONUNBUFFERED=1

# Seed DB on first run, then start pipeline
CMD ["sh", "-c", "python main.py --seed && python main.py"]
