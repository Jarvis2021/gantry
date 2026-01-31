# Contributing to Gantry

Thank you for your interest in contributing to Gantry! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## Branch Protection

> **Important:** The `main` branch is protected. All changes must go through a Pull Request review process.

### Branch Naming Convention

- `feat/<feature-name>` - New features
- `fix/<bug-description>` - Bug fixes
- `docs/<doc-name>` - Documentation changes
- `refactor/<scope>` - Code refactoring
- `test/<test-scope>` - Test additions or fixes

## Pull Request Process

1. **Fork the repository** and create your branch from `develop`
2. **Make your changes** following the coding standards below
3. **Write tests** for any new functionality
4. **Run the test suite** to ensure nothing is broken:
   ```bash
   pytest tests/ -v
   ```
5. **Run linting** to ensure code quality:
   ```bash
   ruff check src/ tests/
   ```
6. **Create a Pull Request** with a clear description of the changes

### PR Requirements

- [ ] All tests pass
- [ ] No linting errors
- [ ] Code follows existing patterns
- [ ] Documentation updated if needed
- [ ] PR description explains the "why" not just the "what"

## Coding Standards

### Python Style

- **Python 3.11+** required
- **Ruff** for linting and formatting
- **Pydantic** for all data models
- **Type hints** on all function signatures
- **Docstrings** for public functions and classes

### Architecture Patterns

Follow the existing layer separation:

```
src/
├── core/       # Business logic (Architect, Fleet, Policy)
├── domain/     # Pydantic models (GantryManifest, etc.)
├── infra/      # External integrations (Docker, Git)
└── main.py     # Flask API entrypoint
```

### File Structure Rules

1. Each module must have a responsibility header comment
2. Maximum 50 lines per function (split if longer)
3. Maximum 3 levels of nesting (use early returns)
4. Imports at top of file (never inside functions)

## Adding New Architectural Skills

Gantry's "Architectural Skills" are capabilities the AI Architect can perform. To add a new skill:

### 1. Define the Skill

Create a new method in `src/core/architect.py`:

```python
def draft_<skill_name>(self, context: dict) -> SomeModel:
    """
    <Skill description>
    
    Args:
        context: Required context for the skill
        
    Returns:
        Validated Pydantic model
    """
    # Implementation
```

### 2. Create the Pydantic Model

Add the response model to `src/domain/models.py`:

```python
class SkillOutput(BaseModel):
    """Output model for <skill_name>."""
    field: str = Field(..., description="What this field represents")
```

### 3. Add Policy Rules (if needed)

Update `policy.yaml` if the skill introduces new security considerations:

```yaml
# New forbidden patterns for <skill>
forbidden_patterns:
  - "dangerous_pattern"
```

### 4. Write Tests

Create `tests/test_<skill>.py`:

```python
def test_skill_happy_path():
    """Test <skill> works correctly."""
    # Arrange, Act, Assert

def test_skill_validation_error():
    """Test <skill> rejects invalid input."""
    # Test edge cases
```

### 5. Update Documentation

- Add skill to README features list
- Document in ARCHITECTURE.md if it changes the flow

## Development Setup

### Prerequisites

- Python 3.11+
- Docker Desktop
- PostgreSQL (or use docker-compose)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/gantry.git
cd gantry

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Start infrastructure
docker-compose up -d gantry_db docker-proxy

# Run the application
python src/main.py
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src --cov-report=html

# Specific test file
pytest tests/test_architect.py -v
```

## Security Guidelines

### Never Commit

- API keys or tokens
- Passwords (even hashed)
- AWS account IDs or ARNs
- `.env` files
- Personal credentials

### Always Use

- Environment variables for secrets
- Placeholder values in examples (`YOUR_API_KEY`)
- `.gitignore` to exclude sensitive files

## Questions?

Open an issue with the `question` label or reach out to the maintainers.

---

*Thank you for helping make Gantry better!*
