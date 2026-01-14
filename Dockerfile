FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Node.js
RUN apt-get update && apt-get install -y \
    gcc \
    pkg-config \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m nltk.downloader vader_lexicon

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /root/ethbot/logs

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Use entrypoint script to route to correct service
CMD ["./entrypoint.sh"]
