FROM python:3.13-slim AS builder

# Set working directory for the builder stage
WORKDIR /app

# Install build dependencies needed for Python wheels
RUN apt-get update && apt-get install -y \
    build-essential \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file to install dependencies
COPY requirements.txt /app/

# Install Python dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir -r /app/requirements.txt

# Second stage: minimal runtime image
FROM python:3.13-slim

# Add metadata labels
LABEL org.opencontainers.image.title="TwitchDropsMinerWeb"
LABEL org.opencontainers.image.description="A tool for mining Twitch drops with web interface"
LABEL org.opencontainers.image.source="https://github.com/Dutchevil/TwitchDropsMinerWeb"
LABEL org.opencontainers.image.vendor="Dutchevil"

# Set working directory
WORKDIR /app

# Install only minimal runtime tools used by the entrypoint/runtime
RUN apt-get update && apt-get install -y \
    ca-certificates \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/logs /app/cache /app/lang

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Verify installations worked
RUN python -c "import yarl; print(f'yarl version: {yarl.__version__}')" && \
    python -c "import aiohttp; print(f'aiohttp version: {aiohttp.__version__}')" && \
    python -c "import requests; print(f'requests version: {requests.__version__}')" && \
    # Create a file listing all installed packages for debugging
    pip freeze > /app/installed_packages.txt

# Set display variable to prevent tkinter from trying to use X server
ENV DISPLAY=''

# Copy source code
COPY *.py ./
COPY web/ ./web/
COPY tests/ ./tests/
COPY lang/ ./lang/
COPY .env.example ./

# Create data directory with appropriate permissions
RUN mkdir -p /data && \
    chmod 755 /data

# Clean up unnecessary cache files to reduce image size
RUN find /opt/venv -name __pycache__ -type d -exec rm -rf {} +  2>/dev/null || true && \
    find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "*.pyo" -delete && \
    find /opt/venv -name "*.pyd" -delete

# Create volume mount points for persistent data
VOLUME ["/app/logs", "/app/cache", "/data"]

# Expose web interface port
EXPOSE 8080

# Copy entrypoint script that handles data persistence
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh && \
    ls -la /app/docker-entrypoint.sh

# Health check for Docker/Portainer/Dockhand. Uses Python stdlib only so no curl/wget is needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\") or os.environ.get(\"WEB_PORT\") or \"8080\"}/health', timeout=4).read()" || exit 1

# Set the entrypoint with web interface enabled and accessible from outside
ENTRYPOINT ["/app/docker-entrypoint.sh"]
