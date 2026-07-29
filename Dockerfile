# Apify Actor base with Playwright (browsers pre-installed)
FROM apify/actor-python-playwright:3.12

# Copy dependency files first for better layer caching
COPY --chown=myuser:myuser requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && echo "Installed packages:" \
    && pip list

# Copy the rest of the source
COPY --chown=myuser:myuser . ./

# Default command: run the Apify Actor entrypoint
CMD ["python", "-m", "src.main"]
