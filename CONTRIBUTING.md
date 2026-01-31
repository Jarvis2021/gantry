# Contributing to Gantry

Thank you for your interest in contributing to Gantry! This document provides guidelines for contributing to the project.

---

## Why Contribute?

Gantry is building the future of AI-powered software development. By contributing, you're helping create:

- The first open-source AI that **deploys production code**
- A **self-healing** CI/CD pipeline
- A **pluggable skills system** for extensibility
- An **audit-first** approach to AI code generation

---

## Architecture Overview

Before contributing, understand Gantry's v2.0 architecture:

```
gantry/
├── src/
│   ├── main_fastapi.py      # FastAPI (async, WebSocket)
│   ├── core/
│   │   ├── architect.py     # AI brain
│   │   ├── auth_v2.py       # Argon2 + TokenBucket
│   │   ├── fleet_v2.py      # Orchestrator (<50 line functions)
│   │   ├── foundry.py       # Docker execution
│   │   ├── policy.py        # Security gate
│   │   ├── deployer.py      # Vercel deployment
│   │   └── publisher.py     # GitHub PR
│   ├── skills/              # Pluggable capabilities
│   │   ├── __init__.py      # Skill registry
│   │   └── consult/         # Example skill
│   └── domain/
│       └── models.py        # Pydantic schemas
├── prompts/                 # External AI prompts (.md files)
│   ├── system.md
│   ├── consult.md
│   └── heal.md
└── tests/
```

---

## Code Quality Standards

Gantry maintains **enterprise-grade code quality**:

| Metric | Standard | Enforcement |
|--------|----------|-------------|
| Function length | **<50 lines** | Ruff lint |
| Type hints | **100%** | MyPy strict |
| Password hashing | **Argon2** | Code review |
| Rate limiting | **Per-user** | TokenBucket |
| API style | **Async** | FastAPI |
| Documentation | **OpenAPI** | Auto-generated |

### Code Review Checklist

- [ ] All functions <50 lines
- [ ] Type hints on all public APIs
- [ ] Pydantic models for data structures
- [ ] No hardcoded secrets
- [ ] Tests for new functionality
- [ ] Docstrings for public functions

---

## Branch Protection

> **Important:** The `main` branch is protected. All changes must go through PR review.

### Branch Naming

| Prefix | Use Case | Example |
|--------|----------|---------|
| `feat/` | New features | `feat/slack-integration` |
| `fix/` | Bug fixes | `fix/websocket-disconnect` |
| `refactor/` | Code improvements | `refactor/fleet-async` |
| `skill/` | New skills | `skill/code-review` |
| `docs/` | Documentation | `docs/api-examples` |

---

## Pull Request Process

### 1. Fork and Branch

```bash
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry
git checkout -b feat/your-feature
```

### 2. Make Changes

Follow the coding standards. Key rules:

```python
# GOOD: Short functions with type hints
async def validate_manifest(manifest: GantryManifest) -> bool:
    """Validate manifest against policy."""
    return policy_gate.validate(manifest)

# BAD: Long functions, no types
def do_stuff(data):
    # 100+ lines of code...
```

### 3. Run Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src --cov-report=html

# Linting
ruff check src/ tests/
```

### 4. Create PR

```bash
git push origin feat/your-feature
# Open PR via GitHub
```

### PR Requirements

- [ ] All tests pass
- [ ] No linting errors
- [ ] Functions <50 lines
- [ ] Type hints added
- [ ] Documentation updated
- [ ] PR description explains "why"

---

## Adding New Skills

The easiest way to contribute is adding a new skill. Skills are **auto-loaded** at startup.

### Step 1: Create Skill Folder

```bash
mkdir -p src/skills/my-skill
```

### Step 2: Create handler.py

```python
# src/skills/my-skill/handler.py
from src.skills import SkillResult

class MySkill:
    """
    My custom skill.
    
    This skill does [description].
    """
    
    name = "my-skill"
    description = "What this skill does"

    async def execute(self, context: dict) -> SkillResult:
        """
        Execute the skill.
        
        Args:
            context: Must contain 'param1', 'param2'
            
        Returns:
            SkillResult with success status and data
        """
        try:
            # Your logic here
            result = {"key": "value"}
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

# Required: expose skill instance
skill = MySkill()
```

### Step 3: Create __init__.py

```python
# src/skills/my-skill/__init__.py
from .handler import skill

__all__ = ["skill"]
```

### Step 4: Create SKILL.md

```markdown
# My Skill

Brief description of what this skill does.

## Usage

\`\`\`python
from src.skills import registry

skill = registry.get("my-skill")
result = await skill.execute({
    "param1": "value1",
    "param2": "value2"
})
\`\`\`

## Input Context

- `param1`: Description
- `param2`: Description

## Output

- `key`: Description of output
```

### Step 5: Add Tests

```python
# tests/test_my_skill.py
import pytest
from src.skills.my_skill import skill

@pytest.mark.asyncio
async def test_my_skill_success():
    """Test skill executes successfully."""
    result = await skill.execute({"param1": "test"})
    assert result.success is True
    assert "key" in result.data

@pytest.mark.asyncio
async def test_my_skill_error():
    """Test skill handles errors gracefully."""
    result = await skill.execute({})  # Missing required param
    assert result.success is False
```

### Step 6: Submit PR

Your skill will be auto-loaded when Gantry starts. No changes to core code needed!

---

## Adding Custom Prompts

Prompts are stored in `prompts/*.md` and loaded dynamically.

### Step 1: Create Prompt File

```markdown
# prompts/my-prompt.md

You are an expert at [task].

## Rules

1. Always do X
2. Never do Y
3. Return JSON format:

\`\`\`json
{
  "field1": "description",
  "field2": "description"
}
\`\`\`
```

### Step 2: Load in Skill

```python
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"

def _load_prompt(name: str) -> str:
    """Load prompt from prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""

# In your skill
class MySkill:
    def __init__(self):
        self._prompt = _load_prompt("my-prompt")
```

---

## Development Setup

### Prerequisites

- Python 3.11+
- Docker Desktop
- PostgreSQL (or use docker-compose)

### Local Setup

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Start infrastructure
docker-compose up -d gantry_db docker-proxy

# Run FastAPI server
python src/main_fastapi.py
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_architect.py -v

# With coverage
pytest tests/ -v --cov=src --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Linting

```bash
# Check code
ruff check src/ tests/

# Auto-fix
ruff check src/ tests/ --fix

# Type checking
mypy src/
```

---

## Security Guidelines

### Never Commit

- API keys or tokens
- Passwords (even hashed)
- AWS account IDs
- `.env` files
- Personal credentials

### Always Use

- Environment variables for secrets
- Placeholder values: `YOUR_API_KEY`
- `.gitignore` to exclude sensitive files

### Password Handling

```python
# GOOD: Use Argon2
from argon2 import PasswordHasher
ph = PasswordHasher()
hashed = ph.hash(password)

# BAD: SHA256, MD5, etc.
import hashlib
hashed = hashlib.sha256(password.encode()).hexdigest()
```

---

## WebSocket Development

When adding real-time features, use the ConnectionManager:

```python
from src.main_fastapi import manager

# In your code
async def some_function(mission_id: str):
    # Broadcast to all connected clients
    await manager.broadcast(mission_id, {
        "type": "custom_event",
        "data": {"key": "value"}
    })
```

---

## Questions?

- Open an issue with the `question` label
- Check existing issues for similar questions
- Read [ARCHITECTURE.md](./ARCHITECTURE.md) for technical details

---

## Recognition

Contributors are recognized in:

- README.md contributors section
- Release notes
- Annual contributor spotlight

---

*Thank you for helping make Gantry the best AI engineering platform!*
