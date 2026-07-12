FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
RUN pip install --no-cache-dir uv && uv pip install --system -e . || pip install -e .
ENV FLASHSCORE_HEADLESS=true PYTHONUNBUFFERED=1
# IaaS ready - expose if using HTTP later
EXPOSE 8000
CMD ["python", "-m", "flashscore_mcp.server"]
