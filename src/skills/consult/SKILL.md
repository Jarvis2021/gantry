# Consult Skill

Multi-turn dialogue with the AI Architect to refine requirements before building.

## Usage

```python
from src.skills import registry

skill = registry.get("consult")
result = await skill.execute({
    "messages": [
        {"role": "user", "content": "Build me a todo app"}
    ]
})
```

## Input Context

- `messages`: List of conversation messages with role and content

## Output

- `response`: Text response to user
- `ready_to_build`: Boolean indicating if user confirmed
- `suggested_stack`: Recommended technology stack
- `app_name`: Suggested application name
- `key_features`: List of suggested features
