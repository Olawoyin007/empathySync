FROM python:3.12-slim

# gosu lets the entrypoint drop privileges cleanly so SIGTERM from
# `docker stop` reaches Streamlit directly (no extra shell layer).
# curl is needed for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only what's needed
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY scenarios/ scenarios/
COPY assets/*.png assets/
COPY .env.example .env.example

# Create data directory
RUN mkdir -p data logs

# Copy .env.example as default if no .env is mounted
RUN cp .env.example .env

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "streamlit", "run", "src/app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
