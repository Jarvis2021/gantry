# Gantry Runbook

> Operational guide for setup, configuration, and troubleshooting the Gantry Fleet v2.0

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture v2.0 Changes](#architecture-v20-changes)
3. [Prerequisites](#prerequisites)
4. [Initial Setup](#initial-setup)
5. [Running Gantry](#running-gantry)
6. [Cloudflare Tunnel Configuration](#cloudflare-tunnel-configuration)
7. [Service Credentials](#service-credentials)
8. [Verification](#verification)
9. [Troubleshooting](#troubleshooting)
10. [Production Deployment](#production-deployment)

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry
cp .env.example .env
# Edit .env with your credentials

# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker-compose up -d

# Run Gantry (FastAPI)
python src/main_fastapi.py

# Open browser
open http://localhost:5050

# View API docs
open http://localhost:5050/docs
```

---

## Architecture v2.0 Changes

If upgrading from v1.0, note these changes:

| Component | v1.0 | v2.0 | Migration |
|-----------|------|------|-----------|
| **API** | Flask (`main.py`) | **FastAPI** (`main_fastapi.py`) | Use new entrypoint |
| **Port** | 5000 | **5050** | Update URLs |
| **Auth** | `auth.py` | **`auth_v2.py`** | Argon2 hashes |
| **Fleet** | `fleet.py` | **`fleet_v2.py`** | Same interface |
| **Real-time** | Polling | **WebSocket `/gantry/ws/{id}`** | Update frontend |

### New Endpoints (v2.0)

| Endpoint | Description |
|----------|-------------|
| `GET /docs` | OpenAPI documentation |
| `WS /gantry/ws/{mission_id}` | WebSocket real-time updates |

### New Folders (v2.0)

| Folder | Purpose |
|--------|---------|
| `prompts/` | External AI prompts |
| `src/skills/` | Pluggable skills |

---

## Prerequisites

### Required Software

| Software | Version | Purpose | Install |
|----------|---------|---------|---------|
| Docker Desktop | 4.0+ | Container runtime | [docker.com](https://docker.com) |
| Python | 3.11+ | API server | [python.org](https://python.org) |
| Git | 2.30+ | Version control | Pre-installed |
| curl | Any | API testing | Pre-installed |

### Required Accounts

| Service | Purpose | Signup |
|---------|---------|--------|
| AWS | Bedrock AI (Claude 3.5) | [aws.amazon.com](https://aws.amazon.com) |
| Cloudflare | Tunnel (optional) | [cloudflare.com](https://cloudflare.com) |
| Vercel | Deployment | [vercel.com](https://vercel.com) |
| GitHub | PR publishing | [github.com](https://github.com) |

---

## Initial Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# OR
.\venv\Scripts\activate   # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**New dependencies in v2.0:**

| Package | Purpose |
|---------|---------|
| `fastapi` | Async API framework |
| `uvicorn` | ASGI server |
| `websockets` | WebSocket support |
| `argon2-cffi` | Password hashing |
| `httpx` | Async HTTP client |

### 4. Create Environment File

```bash
cp .env.example .env
nano .env  # or your editor
```

### 5. Required Environment Variables

```bash
# =============================================================================
# REQUIRED
# =============================================================================

# AI Backend
BEDROCK_API_KEY=your_bedrock_api_key
BEDROCK_REGION=us-east-1

# Authentication (Argon2 hashed automatically)
GANTRY_PASSWORD=your_secure_password

# Database (defaults work with docker-compose)
DB_HOST=gantry_db
DB_PORT=5432
DB_USER=gantry
DB_PASSWORD=securepass
DB_NAME=gantry_fleet

# =============================================================================
# RECOMMENDED
# =============================================================================

# Vercel Deployment
VERCEL_TOKEN=your_vercel_token

# GitHub Publishing
GITHUB_TOKEN=your_github_pat
GITHUB_USERNAME=your_username

# =============================================================================
# OPTIONAL
# =============================================================================

# Pre-hashed password (production)
# GANTRY_PASSWORD_HASH=$argon2id$v=19$m=65536...

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token

# Server port (default: 5050)
GANTRY_PORT=5050
```

---

## Running Gantry

### Option 1: Development Mode (Recommended)

```bash
# Start infrastructure
docker-compose up -d gantry_db docker-proxy

# Run FastAPI with hot reload
uvicorn src.main_fastapi:app --reload --port 5050

# Access
open http://localhost:5050      # Web UI
open http://localhost:5050/docs # API docs
```

### Option 2: Full Docker Stack

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f gantry_core
```

### Option 3: Direct Python

```bash
# Simple start
python src/main_fastapi.py

# Or with uvicorn options
uvicorn src.main_fastapi:app --host 0.0.0.0 --port 5050 --workers 4
```

---

## Cloudflare Tunnel Configuration

The tunnel enables secure public access without port forwarding.

### Step 1: Install cloudflared

```bash
# macOS
brew install cloudflared

# Linux
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

### Step 2: Create Tunnel

```bash
# Login to Cloudflare
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create gantry

# Note the tunnel ID (looks like: abc123-def456-...)
```

### Step 3: Configure DNS

```bash
# Add DNS record
cloudflared tunnel route dns gantry gantry.yourdomain.com
```

### Step 4: Create Config File

```yaml
# ~/.cloudflared/config.yml
tunnel: YOUR_TUNNEL_ID
credentials-file: /path/to/credentials.json

ingress:
  - hostname: gantry.yourdomain.com
    service: http://localhost:5050
  - service: http_status:404
```

### Step 5: Run Tunnel

```bash
# Standalone
cloudflared tunnel run gantry

# Or via docker-compose (already configured)
docker-compose up -d gantry_uplink
```

---

## Service Credentials

### AWS Bedrock

1. Enable Bedrock in AWS Console
2. Request Claude 3.5 Sonnet access
3. Create IAM credentials with Bedrock permissions
4. Add to `.env`:

```bash
BEDROCK_API_KEY=AKIAIOSFODNN7EXAMPLE
```

### Vercel

1. Go to [vercel.com/account/tokens](https://vercel.com/account/tokens)
2. Create new token with deploy permissions
3. Add to `.env`:

```bash
VERCEL_TOKEN=vercel_token_here
```

### GitHub

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Create token with `repo` scope
3. Add to `.env`:

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_USERNAME=your-username
```

---

## Verification

### 1. Health Check

```bash
curl http://localhost:5050/health
# {"status":"online","service":"gantry","version":"2.0.0"}
```

### 2. API Documentation

```bash
open http://localhost:5050/docs
# Should show OpenAPI Swagger UI
```

### 3. Authentication

```bash
# Get auth token
curl -X POST http://localhost:5050/gantry/auth \
  -H "Content-Type: application/json" \
  -d '{"password": "your_password"}'

# Response:
# {"authenticated":true,"token":"abc123...","speech":"Welcome..."}
```

### 4. Chat Mode (Consultation)

```bash
TOKEN="your_token_from_step_3"

curl -X POST http://localhost:5050/gantry/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "messages": [
      {"role": "user", "content": "Build me a todo app"}
    ]
  }'

# Response:
# {"response":"I can build that!...","ready_to_build":false,...}
```

### 5. Voice Mode (One-Shot Build)

```bash
curl -X POST http://localhost:5050/gantry/architect \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"voice_memo": "Build a calculator with dark mode"}'

# Response:
# {"status":"queued","mission_id":"abc-123","speech":"Copy..."}
```

### 6. WebSocket (Real-time)

```javascript
// In browser console or Node.js
const ws = new WebSocket('ws://localhost:5050/gantry/ws/abc-123');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.send('ping');
// Receive: {"type":"pong"}
```

### 7. Web UI

```bash
open http://localhost:5050
# Login with your password
# Start chatting!
```

---

## Troubleshooting

### Common Issues

#### "Connection refused" on port 5050

```bash
# Check if server is running
lsof -i :5050

# Check logs
docker-compose logs gantry_core

# Start manually
python src/main_fastapi.py
```

#### "Module not found" errors

```bash
# Ensure virtual environment is active
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

#### "Argon2 hash mismatch"

Password format changed in v2.0. Reset password:

```bash
# In .env, use plain password (auto-hashed)
GANTRY_PASSWORD=new_password

# Or generate Argon2 hash manually
python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('your_password'))"
```

#### Docker build fails

```bash
# Clean up Docker
docker system prune -a

# Rebuild
docker-compose build --no-cache
docker-compose up -d
```

#### WebSocket not connecting

Check CORS and ensure you're using `ws://` not `http://`:

```javascript
// Correct
new WebSocket('ws://localhost:5050/gantry/ws/mission-id')

// Wrong
new WebSocket('http://localhost:5050/gantry/ws/mission-id')
```

#### "Rate limit exceeded"

v2.0 has per-user rate limiting. Wait 60 seconds or:

```bash
# Restart server to clear rate limits (dev only)
# In production, this is intentional protection
```

#### Database connection failed

```bash
# Check PostgreSQL is running
docker-compose ps gantry_db

# Restart database
docker-compose restart gantry_db

# Check connection
docker-compose exec gantry_db psql -U gantry -d gantry_fleet -c "SELECT 1"
```

### Log Locations

| Service | Log Command |
|---------|-------------|
| Gantry Core | `docker-compose logs -f gantry_core` |
| Database | `docker-compose logs -f gantry_db` |
| Docker Proxy | `docker-compose logs -f docker-proxy` |
| Tunnel | `docker-compose logs -f gantry_uplink` |

---

## Production Deployment

### Pre-deployment Checklist

- [ ] Use strong password (20+ characters)
- [ ] Pre-hash password with Argon2
- [ ] Enable HTTPS via Cloudflare
- [ ] Set up database backups
- [ ] Configure log aggregation
- [ ] Set resource limits in Docker

### Environment Variables (Production)

```bash
# Pre-hashed password (don't store plain text)
GANTRY_PASSWORD_HASH=$argon2id$v=19$m=65536,t=3,p=4$...

# Disable debug
DEBUG=false

# Production database
DB_HOST=your-rds-endpoint.amazonaws.com
DB_PASSWORD=your_strong_db_password

# All services configured
VERCEL_TOKEN=...
GITHUB_TOKEN=...
CLOUDFLARE_TUNNEL_TOKEN=...
```

### Docker Production Config

```yaml
# docker-compose.prod.yml
services:
  gantry_core:
    image: gantry/core:latest
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G
    restart: always
```

### Running in Production

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Monitoring

### Health Endpoint

```bash
# Use for load balancer health checks
curl http://localhost:5050/health
```

### Metrics (Planned)

Prometheus metrics endpoint coming in v2.1:

```bash
curl http://localhost:5050/metrics
```

### Logs

```bash
# Structured JSON logs
docker-compose logs -f gantry_core | jq .
```

---

## Backup and Recovery

### Database Backup

```bash
# Backup
docker-compose exec gantry_db pg_dump -U gantry gantry_fleet > backup.sql

# Restore
docker-compose exec -T gantry_db psql -U gantry gantry_fleet < backup.sql
```

### Mission Evidence

```bash
# Backup missions folder
tar -czf missions-backup.tar.gz missions/

# Restore
tar -xzf missions-backup.tar.gz
```

---

*Last updated: January 2026 | Gantry v2.0*
