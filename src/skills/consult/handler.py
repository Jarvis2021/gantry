# -----------------------------------------------------------------------------
# CONSULT SKILL - Architectural Consultation
# -----------------------------------------------------------------------------
# Multi-turn dialogue with the AI Architect to refine requirements.
# -----------------------------------------------------------------------------

import json
from pathlib import Path

import requests
from pydantic import BaseModel

from src.skills import SkillResult

# Load prompt from external file
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


class ConsultSkill:
    """Consultation skill for multi-turn dialogue."""

    name = "consult"
    description = "Multi-turn dialogue to refine requirements before building"

    def __init__(self) -> None:
        self._prompt = _load_prompt("consult")

    async def execute(self, context: dict) -> SkillResult:
        """
        Execute consultation with the AI Architect.

        Args:
            context: Must contain 'messages' list and 'api_key', 'endpoint', 'model_id'

        Returns:
            SkillResult with consultation response
        """
        messages = context.get("messages", [])
        api_key = context.get("api_key")
        endpoint = context.get("endpoint")
        model_id = context.get("model_id")

        if not all([api_key, endpoint, model_id]):
            return SkillResult(success=False, error="Missing API configuration")

        url = f"{endpoint}/model/{model_id}/invoke"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": self._prompt,
            "messages": messages,
        }

        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)

            if response.status_code != 200:
                return SkillResult(
                    success=False,
                    error=f"API error: {response.status_code}",
                    data={"response": "I'm having trouble connecting. Please try again."},
                )

            response_body = response.json()
            raw_text = response_body["content"][0]["text"]

            # Try to parse as JSON
            try:
                # Extract JSON from response
                first_brace = raw_text.find("{")
                last_brace = raw_text.rfind("}")
                if first_brace != -1 and last_brace != -1:
                    json_str = raw_text[first_brace : last_brace + 1]
                    result = json.loads(json_str)
                    return SkillResult(success=True, data=result)
            except json.JSONDecodeError:
                pass

            return SkillResult(
                success=True,
                data={"response": raw_text, "ready_to_build": False},
            )

        except requests.RequestException as e:
            return SkillResult(success=False, error=f"Request failed: {e}")


# Skill instance for registry
skill = ConsultSkill()
