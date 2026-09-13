# Zenith — runtime image
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps: curl (healthcheck), git/gh (GitHub tools), docker CLI (homelab),
# ffmpeg + espeak-ng + flac (voice STT: normalize browser capture → 16k WAV).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    gnupg \
    docker.io \
    ffmpeg \
    espeak-ng \
    flac \
    && rm -rf /var/lib/apt/lists/* \
    # GitHub CLI (latest release from GitHub's own apt repo)
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers (Chromium headless shell — no full UI needed)
RUN python -m playwright install chromium --with-deps

# App code
COPY zenith ./zenith
COPY run.py .
COPY static ./static
COPY docs ./docs

# Runtime data (SQLite, screenshots, generated files) lives in a volume
RUN mkdir -p /app/data /app/static/screenshots /tmp/zenith-files

EXPOSE 8005

# Entrypoint
CMD ["python", "run.py"]