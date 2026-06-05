FROM python:3.12-slim

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

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["python", "-m", "streamlit", "run", "src/app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
