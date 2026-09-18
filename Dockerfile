# Multi-platform production Dockerfile for GridWise LLM Energy Optimizer
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install system dependencies if required for C-extensions/solvers
RUN apt-get update && apt-get install -y --no-install-recommends \
    coinor-cbc \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code, scripts, and public samples
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY samples/ ./samples/
COPY README.md .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check using Python standard library (no extra curl required)
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + str(__import__('os').environ.get('PORT', 8000)) + '/health').getcode() == 200 else 1)"

EXPOSE 8000

# Start production server
CMD ["sh", "-c", "uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
