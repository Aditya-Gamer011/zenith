# Zenith — Autonomous AI Operating Layer
# Production Multi-Stage Container Image
FROM python:3.13-slim

WORKDIR /app

# Python runtime optimization & headless browser settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/home/zenith \
    HOST=0.0.0.0 \
    PORT=8005 \
    ZENITH_PORT=8005

# System dependencies:
# - curl: container healthcheck & API readiness polling
# - git, ca-certificates, gnupg: secure repo operations
# - ffmpeg, espeak-ng, flac: voice STT/TTS normalization
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    gnupg \
    ffmpeg \
    espeak-ng \
    flac \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root system user and group (Least Privilege Security)
RUN groupadd -g 10001 zenith && \
    useradd -u 10001 -g zenith -m -s /bin/bash zenith

# Install Python application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser dependencies and Chromium headless binary
RUN mkdir -p /ms-playwright && \
    python -m playwright install chromium --with-deps && \
    chmod -R 777 /ms-playwright

# Copy application source tree
COPY zenith ./zenith
COPY run.py .
COPY static ./static
COPY docs ./docs

# Set up runtime data directories with strict non-root ownership
RUN mkdir -p /app/data /app/static/screenshots /tmp/zenith-files && \
    chown -R zenith:zenith /app /tmp/zenith-files

# Switch to non-root execution
USER zenith

# Service port
EXPOSE 8005

# Automated container healthcheck
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8005/api/health || exit 1

# Launch Zenith Cognitive Operating Layer
CMD ["python", "run.py"]