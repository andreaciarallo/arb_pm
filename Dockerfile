# Polymarket Arbitrage Bot
# Base: python:3.12-slim (Debian-based, NOT Alpine — Alpine breaks eth-account/cryptography)
FROM python:3.12-slim

WORKDIR /app

# src/ layout — bot package lives at /app/src/bot/
ENV PYTHONPATH=/app/src

# Install dependencies BEFORE copying application code.
# This layer is cached and only rebuilds when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (separate layer — rebuilds only when src/ changes)
COPY src/ ./src/

# Copy helper scripts (benchmark, API key creation)
COPY scripts/ ./scripts/

# Health check: verifies CLOB API is reachable.
# --start-period=15s: allows time for startup before health checks begin
# --interval=30s: check every 30 seconds
# --timeout=10s: fail if health check takes > 10 seconds
# --retries=3: mark unhealthy after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -m bot.health || exit 1

# Run the bot entrypoint
CMD ["python", "-m", "bot.main"]
