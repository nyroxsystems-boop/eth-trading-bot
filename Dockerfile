FROM python:3.11-slim

WORKDIR /app

# System deps + Node.js
RUN apt-get update && apt-get install -y \
    gcc pkg-config curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Build dashboard
RUN cd dashboard && npm install && npm run build && cd ..

# Logs directory
RUN mkdir -p logs

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["./entrypoint.sh"]
