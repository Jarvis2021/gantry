# Gantry

> **The Headless Fleet Protocol: From Abstract Intent to Production Systems**

[![CI](https://github.com/YOUR_USERNAME/gantry/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/gantry/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Gantry is an autonomous software engineering pipeline that transforms natural language into deployed, production-ready web applications. Whether through voice commands or an interactive chat conversation, Gantry bridges human intent to a local software factory that builds, tests, and deploys code.

## The Gantry Guarantee

1. **"No Touch" Build** - Code is generated and executed inside isolated Project Pods (Docker containers)
2. **"Green Light" Deploy** - Code is only pushed if the Critic Agent passes all audits
3. **"Black Box" Evidence** - Every mission records a cryptographic audit trail

---

## Two Ways to Build

### Chat Mode (Interactive)
Have a conversation with the AI Architect through the web UI. Describe your idea, answer clarifying questions about features and architecture, and confirm when ready to build.

```
You: "Build me a task management app"
Gantry: "I can build that! Here's what I'm thinking:
         - Task list with add/edit/delete
         - Due dates and priorities
         - Local storage for persistence
         Should I build a working prototype with these features?"
You: "Yes, add dark mode too"
Gantry: "Starting build! Watch the Projects panel for progress..."
```

### Voice Mode (One-Shot)
Send a single command via API or iOS Shortcut for quick builds without conversation.

```bash
curl -X POST http://localhost:5000/gantry/architect \
  -H "Content-Type: application/json" \
  -d '{"voice_memo": "Build a todo app with dark mode"}'
```

---

## Key Features

### Conversational Architecture
The AI Architect doesn't just generate code - it reviews your requirements, suggests optimal approaches, asks about scalability, testing, and security, and only builds when you confirm.

### Self-Healing CI/CD
When builds fail, the Architect analyzes errors and generates fixes automatically. Up to 3 repair attempts before escalating to human review.

### Zero-Trust Security
- Docker socket proxy (no direct socket access)
- Policy engine blocks malicious patterns
- Rate limiting and authentication
- Content guardrails filter junk requests

### Junior Dev Model (PR Workflow)
Gantry never pushes directly to main. Every deployment opens a Pull Request for human review, maintaining oversight while enabling automation.

### Multimodal Input
- **Web UI** - Chat interface with projects dashboard
- **Voice** - iOS Shortcuts, Siri integration
- **REST API** - Programmatic access for automation

---

## Architecture Overview

![Gantry Architecture](assets/architecture.png)


> **Note:** GitHub renders Mermaid diagrams as images. If viewing in an editor, see [ARCHITECTURE.md](./ARCHITECTURE.md) for the full diagrams.

---

## Quick Start

### Prerequisites

- Docker Desktop
- Python 3.11+
- AWS Bedrock access (Claude 3.5 Sonnet)
- Vercel account (for deployments)
- GitHub account (for PR workflow)

### 1. Clone and Configure

```bash
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry

# Create environment file
cp .env.example .env

# Edit .env with your credentials
# BEDROCK_API_KEY=your_key
# VERCEL_TOKEN=your_token
# GITHUB_TOKEN=your_token
# GANTRY_PASSWORD=your_password
```

### 2. Start the Fleet

```bash
# Start all services
docker-compose up -d

# Check health
curl http://localhost:5000/health
```

### 3. Open the Web UI

```bash
open http://localhost:5000
```

Login with your password and start chatting!

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI (Chat + Projects dashboard) |
| `/health` | GET | Health check |
| `/gantry/auth` | POST | Authenticate session |
| `/gantry/auth/status` | GET | Check authentication status |
| `/gantry/chat` | POST | Chat with Architect (conversation mode) |
| `/gantry/architect` | POST | Dispatch build mission (one-shot mode) |
| `/gantry/status/<id>` | GET | Get mission status |
| `/gantry/latest` | GET | Get latest mission status |
| `/gantry/missions` | GET | List recent missions |
| `/gantry/search` | GET | Search for similar projects |

### Chat Endpoint

```bash
# Start a conversation
curl -X POST http://localhost:5000/gantry/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Build me a weather dashboard"}
    ]
  }'

# Response includes ready_to_build flag
{
  "response": "I can build that! Here are the features I suggest...",
  "ready_to_build": false,
  "suggested_stack": "node",
  "app_name": "WeatherDashboard",
  "key_features": ["current weather", "5-day forecast", "location search"]
}
```

### Build Endpoint

```bash
# Dispatch a build
curl -X POST http://localhost:5000/gantry/architect \
  -H "Content-Type: application/json" \
  -d '{"voice_memo": "Build a todo app with dark mode"}'

# Wait for completion (sync mode)
curl -X POST "http://localhost:5000/gantry/architect?wait=true" \
  -H "Content-Type: application/json" \
  -d '{"voice_memo": "Build a calculator"}'
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Brain** | AWS Bedrock (Claude 3.5 Sonnet) |
| **Body** | Docker (via Secure Proxy) |
| **Uplink** | Cloudflare Tunnel |
| **Storage** | PostgreSQL (Connection Pooled) |
| **Deploy** | Vercel CLI |
| **Publish** | GitHub API (PR Workflow) |
| **API** | Flask + Pydantic |
| **UI** | Single-page HTML/CSS/JS |

---

## Web UI Features

The Gantry Console provides a modern chat interface:

- **Chat Panel** - Conversational interface with the AI Architect
- **Projects Panel** - Real-time status of all missions
- **Authentication** - Password-protected access
- **Auto-refresh** - Live updates on build progress
- **Mobile Responsive** - Works on phone and tablet

---

## Similar Projects

Gantry shares DNA with other AI agent projects but focuses specifically on **building and deploying software**:

| Project | What It Does | Gantry Difference |
|---------|--------------|-------------------|
| [OpenClaw/Moltworker](https://github.com/cloudflare/moltworker) | Personal AI assistant on Cloudflare | Gantry *deploys code*, OpenClaw *responds to chat* |
| [Devin](https://devin.ai) | AI software engineer | Gantry is open-source, self-hosted |
| [GPT Engineer](https://github.com/gpt-engineer-org/gpt-engineer) | Generate codebases from prompts | Gantry includes deployment + self-healing |
| [Aider](https://github.com/paul-gauthier/aider) | AI pair programming in terminal | Gantry is headless/voice-first with web UI |

See [ARCHITECTURE.md](./ARCHITECTURE.md#comparison-with-similar-projects) for detailed comparison.

---

## Sponsorship

Gantry is open-source and free to use. If you find it valuable, consider supporting development:

### Why Sponsor?

Funds directly support:
- Development of new Architectural Skills
- Security audits and improvements
- Documentation and tutorials
- Community support

### Sponsor Tiers

| Tier | Monthly | Benefits |
|------|---------|----------|
| Supporter | $5 | Name in README |
| Builder | $25 | Priority issue response |
| Architect | $100 | Monthly call + roadmap input |
| Fleet Commander | $500 | Custom skill development |

[Become a Sponsor](https://github.com/sponsors/YOUR_USERNAME)

---

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical deep-dive with Mermaid diagrams
- [RUNBOOK.md](./RUNBOOK.md) - Setup, configuration, and troubleshooting
- [CONTRIBUTING.md](./CONTRIBUTING.md) - How to contribute and add skills

---

## License

MIT License - see [LICENSE](./LICENSE) for details.

---

<p align="center">
  <strong>Gantry</strong> - Your AI Staff Engineer
  <br>
  <em>You describe. Gantry builds.</em>
</p>
