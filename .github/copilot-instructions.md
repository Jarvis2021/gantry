# Copilot Review Instructions for Gantry

When reviewing code in this repository, please follow these guidelines strictly.

## 🎯 Project Context

Gantry is an AI-powered software studio that:
- Generates applications from voice/chat prompts
- Builds them in isolated Docker containers
- Deploys to Vercel with verification
- Opens PRs for human review (never pushes directly to main)

## ✅ Code Quality Standards

### 1. DRY Principle (CRITICAL)
- Flag any duplicated code blocks
- Suggest extraction into helper functions
- Check for repeated patterns across files

### 2. Type Safety
- All functions MUST have type hints
- Return types MUST be specified
- No bare `dict` - use Pydantic models or TypedDict

### 3. Pydantic Usage
- All data structures MUST use Pydantic models
- Validate with `model_validate()` not manual parsing
- Use field validators for complex validation

### 4. Error Handling
- No bare `except:` clauses
- Specific exception types required
- Errors must be logged with context
- Fail fast with clear messages

### 5. Security (NON-NEGOTIABLE)
- NO hardcoded secrets, API keys, or tokens
- NO AWS account IDs or profile names
- Check for credential leaks in:
  - String literals
  - Comments
  - Log messages
  - Error messages

### 6. Docker Safety
- Containers MUST have TTL (timeout)
- MUST use `mem_limit` for resource constraints
- NEVER connect directly to `/var/run/docker.sock`
- ALWAYS use docker-proxy

### 7. Time Complexity
- Flag O(n²) algorithms when O(n) is possible
- Check for nested loops on large datasets
- Suggest appropriate data structures

## 🚫 Auto-Reject Conditions

Flag for immediate rejection if:
1. Secrets/credentials in code
2. Direct push to main branch
3. Missing tests for new functionality
4. Breaking existing tests
5. Swallowing exceptions without logging
6. Bare `except:` clauses
7. Missing type hints on public functions

## 📝 Review Checklist Template

```
### Security
- [ ] No secrets in code
- [ ] No hardcoded credentials
- [ ] Input validation present

### Code Quality
- [ ] DRY principle followed
- [ ] Type hints complete
- [ ] Pydantic models used
- [ ] Error handling proper

### Testing
- [ ] Tests added/updated
- [ ] Coverage maintained

### Architecture
- [ ] Follows existing patterns
- [ ] No unnecessary complexity
- [ ] Single responsibility
```

## 🔧 Common Issues to Flag

1. **Missing await**: Async functions called without await
2. **Resource leaks**: Unclosed files, connections, containers
3. **Race conditions**: Shared state without locks
4. **Import cycles**: Circular dependencies
5. **Magic numbers**: Unexplained numeric constants
6. **Long functions**: >50 lines should be split
7. **Deep nesting**: >3 levels should be flattened

## 📚 Reference Files

When reviewing, cross-reference:
- `.cursorrules` - Project coding standards
- `src/domain/models.py` - Pydantic model patterns
- `src/core/foundry.py` - Docker container patterns
- `src/core/architect.py` - AI integration patterns
