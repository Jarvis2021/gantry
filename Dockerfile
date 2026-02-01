# -----------------------------------------------------------------------------
# GANTRY CORE - THE FLEET MANAGER
# -----------------------------------------------------------------------------
# A headless, voice-activated software factory that orchestrates ephemeral
# "Project Pods" (Docker containers) to build, audit, and deploy software.
#
# Security:
# - Connects to Docker via Secure Proxy (not direct socket)
# - Uses IAM Default Credential Chain (no hardcoded AWS keys)
# - All builds run in isolated sibling containers
# -----------------------------------------------------------------------------

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - gcc: Required for psycopg2 compilation
# - libpq-dev: PostgreSQL client library
# - curl: Health checks
# - git: For GitHub publishing (PR workflow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and config
COPY src/ /app/src/
COPY policy.yaml /app/policy.yaml

# Create missions directory for evidence packs
RUN mkdir -p /app/missions

# Expose FastAPI port
EXPOSE 5050

# Health check (enhanced 2026 pattern with /ready endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5050/health || exit 1

# Copy skills and prompts directories
COPY src/skills/ /app/src/skills/
COPY prompts/ /app/prompts/

# Run FastAPI with uvicorn (async, WebSocket support)
CMD ["uvicorn", "src.main_fastapi:app", "--host", "0.0.0.0", "--port", "5050"]
