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
4. **ALL projects MUST be WEB APPLICATIONS** - they will be deployed to Vercel.

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

VERCEL DEPLOYMENT REQUIREMENT:
Every project MUST be a web application accessible via HTTP. Vercel will serve it.

For Python: Create a Flask or FastAPI app with at least one HTTP route (e.g., GET /).
For Node: Create an Express server or use Vercel serverless functions.

STACK GUIDELINES:

Python (Vercel Serverless - REQUIRED):
- Use the BaseHTTPRequestHandler format for Vercel Python serverless.
- Include api/index.py with this EXACT format:
  ```
  from http.server import BaseHTTPRequestHandler
  import json
  import random
  
  class handler(BaseHTTPRequestHandler):
      def do_GET(self):
          self.send_response(200)
          self.send_header('Content-type', 'application/json')
          self.end_headers()
          data = {"message": "Hello from Gantry!"}
          self.wfile.write(json.dumps(data).encode())
          return
  ```
- NO requirements.txt needed for basic JSON APIs (only stdlib).
- Include vercel.json: {"rewrites":[{"source":"/(.*)", "destination":"/api"}]}
- For audit_command: "python -m py_compile api/index.py"
- DO NOT use Flask for Vercel. Use BaseHTTPRequestHandler.

Node (Express - REQUIRED for web):
- ALWAYS create an Express web server with HTTP routes.
- Include api/index.js for Vercel serverless:
  ```
  module.exports = (req, res) => {
    res.status(200).json({ message: "Hello from Gantry!" });
  };
  ```
- Include package.json with dependencies.
- Include vercel.json if needed.
- For audit_command: "npm install && node -c api/index.js"

IMPORTANT: 
- The base images are minimal. Install packages first in audit_command.
- NEVER create console-only scripts. ALWAYS create web-accessible endpoints."""

# System prompt for self-healing / debugging
HEAL_PROMPT = """You are a Senior Debugger for the Gantry Build System. The previous build FAILED.

Your task: Analyze the error log and the original manifest, then return a NEW, CORRECTED GantryManifest that fixes the issue.

CRITICAL RULES:
1. Output ONLY valid JSON matching the GantryManifest schema.
2. NO markdown, NO explanation, NO commentary.
3. FIX the specific error shown in the logs.
4. Common fixes include: missing imports, missing dependencies in requirements.txt, syntax errors, wrong file paths.

SCHEMA:
{
  "project_name": "string (keep the same name)",
  "stack": "python" | "node" | "rust",
  "files": [
    {"path": "relative/path.ext", "content": "CORRECTED file content"}
  ],
  "audit_command": "command to verify the build",
  "run_command": "command to run the app"
}

DEBUGGING CHECKLIST:
- ModuleNotFoundError/ImportError → Add missing import or add to requirements.txt
- SyntaxError → Fix the syntax in the indicated file/line
- FileNotFoundError → Check file paths match what code expects
- npm/pip install errors → Check package names are correct
- Test failures → Fix the code logic

Return the COMPLETE corrected manifest with ALL files, not just the changed ones."""


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

    def heal_blueprint(
        self, 
        original_manifest: GantryManifest, 
        error_log: str
    ) -> GantryManifest:
        """
        Self-Healing: Analyze error and generate a fixed manifest.
        
        This is the "Repair" skill that makes Gantry agentic.
        When a build fails, the Architect reads the error and fixes the code.
        
        Args:
            original_manifest: The manifest that failed.
            error_log: The error output from the failed audit.
            
        Returns:
            A new, corrected GantryManifest.
            
        Raises:
            ArchitectError: If healing fails.
        """
        console.print(f"[yellow][ARCHITECT] Self-healing: analyzing failure...[/yellow]")
        
        # Build the healing prompt with context
        healing_request = f"""## FAILED BUILD - NEEDS FIX

### Original Manifest:
```json
{json.dumps(original_manifest.model_dump(), indent=2)}
```

### Error Log:
```
{error_log[:2000]}
```

Analyze the error and return a CORRECTED GantryManifest that fixes this issue."""
        
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
            "system": HEAL_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": healing_request
                }
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=body, timeout=60)
            
            if response.status_code != 200:
                console.print(f"[red][ARCHITECT] Healing API error: {response.status_code}[/red]")
                raise ArchitectError(f"Healing failed: {response.status_code}")
            
            response_body = response.json()
            raw_text = response_body["content"][0]["text"]
            
            console.print("[cyan][ARCHITECT] Healing response received, parsing...[/cyan]")
            
        except requests.RequestException as e:
            console.print(f"[red][ARCHITECT] Healing request failed: {e}[/red]")
            raise ArchitectError(f"Healing request failed: {e}") from e
        except (KeyError, IndexError) as e:
            console.print(f"[red][ARCHITECT] Unexpected healing response[/red]")
            raise ArchitectError(f"Unexpected response: {e}") from e
        
        # Clean and parse JSON
        try:
            clean_json = self._clean_json(raw_text)
            manifest_data = json.loads(clean_json)
        except json.JSONDecodeError as e:
            console.print(f"[red][ARCHITECT] Healing JSON parse failed[/red]")
            raise ArchitectError(f"Invalid healing JSON: {e}") from e
        
        # Validate with Pydantic
        try:
            healed_manifest = GantryManifest(**manifest_data)
            console.print(f"[green][ARCHITECT] Healed blueprint ready: {healed_manifest.project_name}[/green]")
            return healed_manifest
        except ValidationError as e:
            console.print(f"[red][ARCHITECT] Healed manifest validation failed[/red]")
            raise ArchitectError(f"Healed manifest invalid: {e}") from e
