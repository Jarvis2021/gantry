# -----------------------------------------------------------------------------
# THE BRAIN - BEDROCK ARCHITECT
# -----------------------------------------------------------------------------
# Responsibility: Uses AWS Bedrock (Claude 3.5 Sonnet) to draft the
# Fabrication Instructions (GantryManifest) from a voice memo.
#
# Authentication: Uses Bedrock API Key (simpler than IAM).
# -----------------------------------------------------------------------------

import json
import os
import re
from typing import Optional

import requests
from pydantic import ValidationError
from rich.console import Console

from src.domain.models import GantryManifest

console = Console()

# Bedrock API configuration
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
BEDROCK_ENDPOINT = f"https://bedrock-runtime.{BEDROCK_REGION}.amazonaws.com"
CLAUDE_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"

# System prompt that constrains Claude to output valid JSON
SYSTEM_PROMPT = """You are the Gantry Chief Architect. Your task is to generate Fabrication Instructions for Project Pods.

CRITICAL RULES:
1. Output ONLY valid JSON matching the GantryManifest schema.
2. NO markdown, NO explanation, NO commentary.
3. The JSON must be parseable directly.

SCHEMA:
{
  "project_name": "string (alphanumeric, starts with letter, max 64 chars)",
  "stack": "python" | "node" | "rust",
  "files": [
    {"path": "relative/path.ext", "content": "file content here"}
  ],
  "audit_command": "command to verify the build works",
  "run_command": "command to deploy the app"
}

STACK GUIDELINES:

Python:
- If you need external packages, include a requirements.txt file.
- For audit_command, use commands that DON'T require external packages if possible.
- GOOD audit commands: "python -m py_compile *.py", "python main.py", "python -c 'import app'"
- If you need pytest, include it in requirements.txt and use: "pip install -r requirements.txt && pytest"

Node:
- Include package.json with dependencies.
- For audit_command use: "npm install && npm test" (always install first)

Rust:
- Include Cargo.toml.
- For audit_command use: "cargo build" or "cargo test"

IMPORTANT: The base images are minimal (python:3.11-slim, node:20-alpine, rust:1.75-slim).
If your audit_command needs packages, ALWAYS install them first in the command."""


class ArchitectError(Exception):
    """Raised when the Architect fails to generate a valid manifest."""
    pass


class Architect:
    """
    The AI Brain that translates voice memos into Fabrication Instructions.
    
    Uses Bedrock API Key for authentication.
    """

    def __init__(self, api_key: Optional[str] = None, region: str = BEDROCK_REGION) -> None:
        """
        Initialize the Bedrock client using API Key.
        
        Args:
            api_key: Bedrock API key. Defaults to BEDROCK_API_KEY env var.
            region: AWS region for Bedrock.
        
        Raises:
            ArchitectError: If API key is not provided.
        """
        self._api_key = api_key or os.getenv("BEDROCK_API_KEY")
        self._region = region
        self._endpoint = f"https://bedrock-runtime.{self._region}.amazonaws.com"
        
        if not self._api_key:
            console.print("[red][ARCHITECT] BEDROCK_API_KEY not found[/red]")
            raise ArchitectError("BEDROCK_API_KEY environment variable not set")
        
        console.print(f"[green][ARCHITECT] Brain online (region: {self._region})[/green]")

    def _clean_json(self, text: str) -> str:
        """
        Extract valid JSON from Claude's response.
        
        Why: Claude sometimes wraps JSON in markdown or adds commentary.
        This regex helper strips everything except the JSON object.
        """
        # Find JSON object boundaries
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        
        if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
            raise ArchitectError(f"No valid JSON in response: {text[:200]}...")
        
        json_str = text[first_brace:last_brace + 1]
        
        # Fix common LLM JSON errors
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        
        return json_str

    def draft_blueprint(self, prompt: str) -> GantryManifest:
        """
        Draft Fabrication Instructions from a voice memo.
        
        Args:
            prompt: The user's voice memo / build request.
            
        Returns:
            A validated GantryManifest ready for the Foundry.
            
        Raises:
            ArchitectError: If Claude fails or returns invalid JSON.
        """
        console.print(f"[cyan][ARCHITECT] Drafting blueprint: {prompt[:50]}...[/cyan]")
        
        # Prepare request
        url = f"{self._endpoint}/model/{CLAUDE_MODEL_ID}/invoke"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=body, timeout=60)
            
            if response.status_code != 200:
                console.print(f"[red][ARCHITECT] API error: {response.status_code}[/red]")
                console.print(f"[red]{response.text}[/red]")
                raise ArchitectError(f"Bedrock API error: {response.status_code} - {response.text}")
            
            response_body = response.json()
            raw_text = response_body["content"][0]["text"]
            
            console.print("[cyan][ARCHITECT] Response received, parsing...[/cyan]")
            
        except requests.RequestException as e:
            console.print(f"[red][ARCHITECT] Request failed: {e}[/red]")
            raise ArchitectError(f"Bedrock API request failed: {e}") from e
        except (KeyError, IndexError) as e:
            console.print(f"[red][ARCHITECT] Unexpected response format[/red]")
            raise ArchitectError(f"Unexpected Bedrock response: {e}") from e
        
        # Clean and parse JSON
        try:
            clean_json = self._clean_json(raw_text)
            manifest_data = json.loads(clean_json)
        except json.JSONDecodeError as e:
            console.print(f"[red][ARCHITECT] JSON parsing failed[/red]")
            raise ArchitectError(f"Invalid JSON: {e}") from e
        
        # Validate with Pydantic
        try:
            manifest = GantryManifest(**manifest_data)
            console.print(f"[green][ARCHITECT] Blueprint ready: {manifest.project_name}[/green]")
            return manifest
        except ValidationError as e:
            console.print(f"[red][ARCHITECT] Manifest validation failed[/red]")
            raise ArchitectError(f"Manifest validation failed: {e}") from e
