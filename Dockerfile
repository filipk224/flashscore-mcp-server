# Production Dockerfile for IaaS (Railway, Fly.io, AWS ECS, DigitalOcean, etc.)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# System deps already in base
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data

RUN pip install --no-cache-dir uv \
    && uv pip install --system -e . \
    && playwright install-deps chromium || true

ENV FLASHSCORE_HEADLESS=true \
    PYTHONUNBUFFERED=1 \
    FLASHSCORE_MAX_CONCURRENT_PAGES=2 \
    FLASHSCORE_MIN_DELAY_S=1.8

# Healthcheck for IaaS
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import flashscore_mcp; print('ok')" || exit 1

# Default: stdio. For hosted HTTP/SSE override CMD or use platform start command
CMD ["python", "-m", "flashscore_mcp.server"]
