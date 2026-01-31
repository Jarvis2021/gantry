# Gantry Runbook

> Operational guide for setup, configuration, and troubleshooting

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Cloudflare Tunnel Configuration](#cloudflare-tunnel-configuration)
4. [Python Environment](#python-environment)
5. [Docker Configuration](#docker-configuration)
6. [Database Setup](#database-setup)
7. [Service Credentials](#service-credentials)
8. [Verification](#verification)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Docker Desktop | 4.0+ | Container runtime |
| Python | 3.11+ | Local development |
| Git | 2.30+ | Version control |
| curl | Any | API testing |

### Required Accounts

| Service | Purpose | Signup |
|---------|---------|--------|
| AWS | Bedrock AI access | [aws.amazon.com](https://aws.amazon.com) |
| Cloudflare | Tunnel for public access | [cloudflare.com](https://cloudflare.com) |
| Vercel | Deployment hosting | [vercel.com](https://vercel.com) |
| GitHub | Code publishing | [github.com](https://github.com) |

---

## Initial Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry
```

### 2. Create Environment File

```bash
# Copy template
cp .env.example .env

# Edit with your values
nano .env
```

### 3. Required Environment Variables

```bash
# Bedrock AI (required)
BEDROCK_API_KEY=your_bedrock_api_key
BEDROCK_REGION=us-east-1

# Authentication (required)
GANTRY_PASSWORD=your_secure_password
SECRET_KEY=random-32-character-string

# Database (defaults provided in docker-compose)
DB_HOST=gantry_db
DB_PORT=5432
DB_USER=gantry
DB_PASSWORD=securepass
DB_NAME=gantry_fleet

# Vercel Deployment (optional but recommended)
VERCEL_TOKEN=your_vercel_token

# GitHub Publishing (optional but recommended)
GITHUB_TOKEN=your_github_pat
GITHUB_USERNAME=your_github_username

# Cloudflare Tunnel (for public access)
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token
```

---

## Cloudflare Tunnel Configuration

The tunnel enables secure access from the internet without opening ports.

### Step 1: Create a Tunnel

```bash
# Install cloudflared CLI
brew install cloudflared

# Login to Cloudflare
cloudflared tunnel login

# Create a new tunnel
cloudflared tunnel create gantry

# Note the tunnel ID displayed
```

### Step 2: Configure the Tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: ~/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: api.gantryfleet.ai
    service: http://gantry_core:5000
  - service: http_status:404
```

### Step 3: Add DNS Record

```bash
# Add CNAME pointing to tunnel
cloudflared tunnel route dns gantry api.gantryfleet.ai
```

### Step 4: Get Tunnel Token

```bash
# Generate token for docker-compose
cloudflared tunnel token gantry

# Copy the token to .env
CLOUDFLARE_TUNNEL_TOKEN=the_generated_token
```

### Step 5: Verify Tunnel

```bash
# Start the tunnel container
docker-compose up -d gantry_uplink

# Check logs
docker logs gantry_uplink

# Should see: "Connection registered"
```

---

## Python Environment

### Local Development Setup

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install pytest pytest-cov ruff
```

### Run Locally (without Docker)

```bash
# Start PostgreSQL (via Docker)
docker-compose up -d gantry_db

# Wait for database
sleep 5

# Run the application
python src/main.py
```

---

## Docker Configuration

### Build the Images

```bash
# Build main application
docker build -t gantry/core:latest .

# Build builder image (for Project Pods)
docker build -f builder.Dockerfile -t gantry/builder:latest .
```

### Start All Services

```bash
# Start everything
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f gantry_core
```

### Service Ports

| Service | Internal Port | External Port |
|---------|--------------|---------------|
| gantry_core | 5000 | 5000 |
| gantry_db | 5432 | - |
| docker-proxy | 2375 | - |
| gantry_uplink | - | - |

---

## Database Setup

### Automatic Migration

The database schema is created automatically on startup via `init_db()`.

### Manual Access

```bash
# Connect to PostgreSQL
docker exec -it gantry_db psql -U gantry -d gantry_fleet

# Common queries
SELECT id, status, created_at FROM missions ORDER BY created_at DESC LIMIT 10;

# Check table schema
\d missions
```

### Reset Database

```bash
# Stop services
docker-compose down

# Remove volume
docker volume rm gantry_pgdata

# Restart (recreates schema)
docker-compose up -d
```

---

## Service Credentials

### AWS Bedrock

1. Go to AWS Console > Bedrock > Model Access
2. Request access to Claude 3.5 Sonnet
3. Create API key or use IAM role
4. Set `BEDROCK_API_KEY` in `.env`

### Vercel

1. Go to vercel.com > Settings > Tokens
2. Create a new token with full access
3. Set `VERCEL_TOKEN` in `.env`

### GitHub

1. Go to github.com > Settings > Developer Settings > PAT
2. Create a fine-grained token with:
   - Repository: All repositories (or specific)
   - Permissions: Contents (read/write), Pull Requests (read/write)
3. Set `GITHUB_TOKEN` and `GITHUB_USERNAME` in `.env`

---

## Verification

### Step 1: Health Check

```bash
curl http://localhost:5000/health
# Expected: {"status": "online", "service": "gantry"}
```

### Step 2: Authentication

```bash
# Authenticate
curl -X POST http://localhost:5000/gantry/auth \
  -H "Content-Type: application/json" \
  -d '{"password": "your_password"}'

# Expected: {"authenticated": true}
```

### Step 3: Test Chat Mode (Consultation)

```bash
# Start a conversation with the Architect
curl -X POST http://localhost:5000/gantry/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Build me a simple calculator"}
    ]
  }'

# Expected: {"response": "...", "ready_to_build": false, "suggested_stack": "node", ...}

# The Architect will suggest features and ask for confirmation
# When you confirm, ready_to_build becomes true
```

### Step 4: Test Voice Mode (One-Shot Build)

```bash
# Dispatch a build directly (skip consultation)
curl -X POST http://localhost:5000/gantry/architect \
  -H "Content-Type: application/json" \
  -d '{"voice_memo": "Build a hello world page", "deploy": false, "publish": false}'

# Expected: {"status": "queued", "mission_id": "..."}
```

### Step 5: Check Status

```bash
curl http://localhost:5000/gantry/status/YOUR_MISSION_ID

# Expected: {"status": "BUILDING", "speech": "..."}
# Poll until status is DEPLOYED, SUCCESS, or FAILED
```

### Step 6: Open Web UI

```bash
open http://localhost:5000
```

1. Enter your password to login
2. Start a conversation: "Build me a todo app"
3. The Architect will suggest features
4. Confirm to start the build
5. Watch the Projects panel for progress

### Step 7: Mobile Connection (via Tunnel)

```bash
curl https://api.gantryfleet.ai/health
# Should return same as localhost
```

---

## Troubleshooting

### Common Issues

#### 1. "Connection refused" on localhost:5000

**Cause:** Flask not running or port conflict.

**Solution:**
```bash
# Check if port is in use
lsof -i :5000

# Check container logs
docker logs gantry_core

# Restart the service
docker-compose restart gantry_core
```

#### 2. "Database connection failed"

**Cause:** PostgreSQL not ready or credentials wrong.

**Solution:**
```bash
# Check database container
docker logs gantry_db

# Verify credentials match .env and docker-compose.yml
grep DB_ .env

# Test direct connection
docker exec -it gantry_db pg_isready -U gantry
```

#### 3. "Architect failed" / "BEDROCK_API_KEY not found"

**Cause:** Missing or invalid Bedrock credentials.

**Solution:**
```bash
# Verify key is set
grep BEDROCK .env

# Test Bedrock access (AWS CLI)
aws bedrock-runtime invoke-model --model-id anthropic.claude-3-5-sonnet-20240620-v1:0 ...

# Check logs for specific error
docker logs gantry_core | grep ARCHITECT
```

#### 4. "Tunnel not connecting"

**Cause:** Invalid tunnel token or DNS not propagated.

**Solution:**
```bash
# Check tunnel logs
docker logs gantry_uplink

# Verify token
cloudflared tunnel info gantry

# Test DNS resolution
dig api.gantryfleet.ai

# Regenerate token if needed
cloudflared tunnel token gantry
```

#### 5. "Build timeout" / "Dead Man's Switch triggered"

**Cause:** Build taking too long (>180s).

**Solution:**
- Check if Docker has enough resources
- Simplify the build request
- Check container logs for what's hanging

```bash
# Find stuck containers
docker ps | grep gantry_

# Check container logs
docker logs gantry_MISSION_ID

# Force cleanup
docker kill gantry_MISSION_ID
```

#### 6. "Vercel deployment failed"

**Cause:** Invalid token, project config, or Vercel limits.

**Solution:**
```bash
# Verify token
VERCEL_TOKEN=your_token vercel whoami

# Check project structure in mission folder
ls -la missions/MISSION_ID/

# Look for vercel.json issues
cat missions/MISSION_ID/manifest.json | jq '.files[] | select(.path | contains("vercel"))'
```

#### 7. "GitHub PR creation failed"

**Cause:** Token permissions, branch issues, or rate limiting.

**Solution:**
```bash
# Test token
curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user

# Check rate limits
curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit

# Verify token has repo scope
# Must have: Contents (read/write), Pull Requests (read/write)
```

### Log Locations

| Log | Location |
|-----|----------|
| Flask API | `docker logs gantry_core` |
| Database | `docker logs gantry_db` |
| Tunnel | `docker logs gantry_uplink` |
| Mission Evidence | `missions/{id}/flight_recorder.json` |

### Support

For issues not covered here:

1. Check `missions/{id}/flight_recorder.json` for detailed event log
2. Search existing GitHub issues
3. Open a new issue with:
   - Error message
   - Relevant log output
   - Steps to reproduce

---

*Last updated: 2026*
