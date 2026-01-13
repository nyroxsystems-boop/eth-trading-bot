FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    pkg-config \
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

# Default command (can be overridden by Railway)
CMD ["python3", "eth_master_bot.py"]
