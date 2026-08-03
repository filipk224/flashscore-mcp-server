# =============================================================================
# Flashscore MCP Server – IaaS / Cloud ready Dockerfile
# =============================================================================
# Base image includes Python 3.12 + Playwright browsers (Chromium etc.).
# Works on: Railway, Fly.io, Render, DigitalOcean, AWS ECS, Cloud Run, etc.
# Also remains compatible with Apify Actor deployment.
# =============================================================================

FROM apify/actor-python-playwright:3.12

# Runtime environment defaults (override via platform env vars)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8000 \
    HOST=0.0.0.0 \
    FLASHSCORE_HEADLESS=true \
    FLASHSCORE_MAX_CONCURRENT_PAGES=2 \
    FLASHSCORE_MIN_DELAY_S=1.8

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY --chown=myuser:myuser requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip list

# Copy application source
COPY --chown=myuser:myuser . .

# Ensure cache directory exists and is writable
RUN mkdir -p /app/data && chown -R myuser:myuser /app/data

# Expose the HTTP port used by the MCP server
EXPOSE 8000

# Basic health check – verifies the process is listening (MCP endpoint)
# Platforms that support HEALTHCHECK will use this; others ignore it.
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', int(__import__('os').environ.get('PORT', '8000')))); s.close()" || exit 1

# Default command for general IaaS / Docker hosts
# (Apify can override via Actor settings or use src/main.py if preferred)
CMD ["python", "-m", "flashscore_mcp.http_server"]
