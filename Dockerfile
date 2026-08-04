# =============================================================================
# Flashscore MCP Server – Pure IaaS / Streamable HTTP Dockerfile
# =============================================================================
# Official Microsoft Playwright Python image (no Apify, no xvfb-entrypoint).
# Intended for Rumble Cloud, Railway, Fly.io, Render, DigitalOcean, etc.
# For Apify Actor deployment use Dockerfile.apify instead.
# =============================================================================

FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8000 \
    HOST=0.0.0.0 \
    FLASHSCORE_HEADLESS=true \
    FLASHSCORE_MAX_CONCURRENT_PAGES=2 \
    FLASHSCORE_MIN_DELAY_S=1.8 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install Python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip list

# Application source
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=15s --start-period=45s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', int(__import__('os').environ.get('PORT', '8000')))); s.close()" || exit 1

# Pure streamable-HTTP entrypoint (no Apify, no Xvfb)
CMD ["python", "-m", "flashscore_mcp.http_server"]
