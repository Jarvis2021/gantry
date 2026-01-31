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
SYSTEM_PROMPT = """You are the Gantry Chief Architect. Generate REAL WEB APPLICATIONS with beautiful UI.

CRITICAL RULES:
1. Output ONLY valid JSON matching the GantryManifest schema.
2. NO markdown, NO explanation, NO commentary - just pure JSON.
3. Build REAL web apps with HTML/CSS/JavaScript UI - NOT just JSON APIs.
4. Make the UI beautiful, modern, and functional.

SCHEMA:
{
  "project_name": "string (alphanumeric, starts with letter, max 64 chars)",
  "stack": "node",
  "files": [{"path": "relative/path.ext", "content": "file content here"}],
  "audit_command": "command to verify the build works",
  "run_command": "command to run the app locally"
}

=== BUILD REAL WEB APPLICATIONS ===

ALWAYS create these files:

1. **public/index.html** - The main HTML page with embedded CSS and JavaScript
2. **api/index.js** - Backend API if needed (Vercel serverless)
3. **vercel.json** - Configuration
4. **package.json** - Minimal config

=== EXAMPLE: Todo App ===

public/index.html:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Todo App</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; }
    .container { background: white; padding: 2rem; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 400px; }
    h1 { color: #333; margin-bottom: 1rem; text-align: center; }
    .input-group { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
    input { flex: 1; padding: 0.75rem; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1rem; }
    input:focus { outline: none; border-color: #667eea; }
    button { padding: 0.75rem 1.5rem; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
    button:hover { background: #5a6fd6; }
    ul { list-style: none; }
    li { padding: 0.75rem; background: #f8f9fa; margin-bottom: 0.5rem; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }
    li.done { text-decoration: line-through; opacity: 0.6; }
    .delete { background: #ff4757; padding: 0.25rem 0.5rem; font-size: 0.8rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>My Todos</h1>
    <div class="input-group">
      <input type="text" id="input" placeholder="Add a todo...">
      <button onclick="addTodo()">Add</button>
    </div>
    <ul id="list"></ul>
  </div>
  <script>
    let todos = JSON.parse(localStorage.getItem('todos') || '[]');
    function render() {
      document.getElementById('list').innerHTML = todos.map((t, i) =>
        `<li class="${t.done ? 'done' : ''}" onclick="toggle(${i})">${t.text} <button class="delete" onclick="event.stopPropagation();del(${i})">x</button></li>`
      ).join('');
    }
    function addTodo() {
      const input = document.getElementById('input');
      if (input.value.trim()) {
        todos.push({ text: input.value.trim(), done: false });
        input.value = '';
        save(); render();
      }
    }
    function toggle(i) { todos[i].done = !todos[i].done; save(); render(); }
    function del(i) { todos.splice(i, 1); save(); render(); }
    function save() { localStorage.setItem('todos', JSON.stringify(todos)); }
    document.getElementById('input').addEventListener('keypress', e => { if (e.key === 'Enter') addTodo(); });
    render();
  </script>
</body>
</html>
```

vercel.json (routes static files and API):
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.js" }
  ]
}
```

package.json:
```json
{"name": "todo-app", "version": "1.0.0"}
```

=== DESIGN REQUIREMENTS ===
1. Use modern CSS: gradients, shadows, rounded corners, flexbox/grid
2. Make it VISUALLY IMPRESSIVE - use colors, animations
3. Mobile responsive (use viewport meta, relative units)
4. Interactive with JavaScript (not just static HTML)
5. Include proper error handling and loading states

=== FOR DIFFERENT APP TYPES ===
- **Dashboard**: Cards, charts (use CSS or simple canvas), stats
- **Landing Page**: Hero section, features, call-to-action buttons
- **Calculator**: Buttons grid, display, interactive calculations
- **Game**: Canvas or DOM-based, score tracking, animations
- **Form App**: Input validation, success/error messages, submissions

=== AUDIT COMMAND ===
For audit: "node -e \"console.log('Build OK')\"" (simple validation)

NEVER return just JSON APIs - always build COMPLETE web applications with beautiful UI."""

# System prompt for self-healing / debugging
# System prompt for architectural consultation
CONSULT_PROMPT = """You are the Gantry Chief Architect - an expert who builds REAL web applications with beautiful UI.

YOUR ROLE:
Analyze requests and suggest the best approach. Be confident and specific. Explain:
- What the app will look like (UI/UX)
- Key features and interactivity
- How it handles data (localStorage, API calls, etc.)
- Mobile responsiveness

Keep responses to 2-3 short paragraphs. End with: "Ready to proceed? Say 'yes' to start building."

WHAT YOU BUILD:
- REAL web applications with HTML/CSS/JavaScript
- Beautiful, modern UI (gradients, shadows, animations)
- Interactive features (not just static pages)
- Mobile-responsive designs
- Deployed instantly to Vercel with live URL

EXAMPLES OF WHAT YOU BUILD:
- Todo apps with add/complete/delete functionality
- Calculators with button grids and display
- Dashboards with cards and stats
- Landing pages with hero sections
- Games with canvas/DOM animations
- Forms with validation

OUTPUT FORMAT (strict JSON, no markdown):
{"response": "PLAIN TEXT response here", "ready_to_build": false, "suggested_stack": "node", "app_name": "AppName", "app_type": "Web App", "key_features": ["feature1", "feature2"]}

CRITICAL: The "response" field must contain PLAIN TEXT only. Write naturally.

If user confirms with "yes", "ok", "proceed", "build", "go" → set ready_to_build: true"""

HEAL_PROMPT = """You are a Senior Debugger for the Gantry Build System. The previous build FAILED.

Analyze the error and return a CORRECTED GantryManifest.

CRITICAL RULES:
1. Output ONLY valid JSON - no markdown, no commentary.
2. FIX the specific error shown in the logs.
3. Return ALL files, not just changed ones.
4. Build REAL web apps with HTML/CSS/JS UI, not just APIs.

SCHEMA:
{
  "project_name": "string (keep same name)",
  "stack": "node",
  "files": [{"path": "path.ext", "content": "CORRECTED content"}],
  "audit_command": "command to verify",
  "run_command": "command to run"
}

COMMON FIXES:
- SyntaxError → Fix the syntax at indicated line
- Missing file → Add the required file
- HTML not rendering → Ensure public/index.html exists with proper HTML
- API errors → Fix the serverless function in api/index.js

IMPORTANT: Always include public/index.html with real HTML/CSS/JS UI.

Return COMPLETE corrected manifest with ALL files."""


class ArchitectError(Exception):
    """Raised when the Architect fails to generate a valid manifest."""

    pass


class Architect:
    """
    The AI Brain that translates voice memos into Fabrication Instructions.

    Uses Bedrock API Key for authentication.
    """

    def __init__(self, api_key: str | None = None, region: str = BEDROCK_REGION) -> None:
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

        Why: Claude sometimes wraps JSON in markdown, adds commentary,
        or outputs JSON with literal control characters that need escaping.
        """
        # Find JSON object boundaries
        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
            raise ArchitectError(f"No valid JSON in response: {text[:200]}...")

        json_str = text[first_brace : last_brace + 1]

        # Fix common LLM JSON errors (trailing commas)
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)

        # Try to parse, if it fails, attempt to fix control characters
        try:
            json.loads(json_str)  # Test parse
            return json_str
        except json.JSONDecodeError:
            # Escape unescaped control characters in string values
            # Replace literal newlines/tabs with escaped versions
            result = []
            in_string = False
            escape_next = False

            for char in json_str:
                if escape_next:
                    result.append(char)
                    escape_next = False
                elif char == "\\":
                    result.append(char)
                    escape_next = True
                elif char == '"':
                    result.append(char)
                    in_string = not in_string
                elif in_string and char == "\n":
                    result.append("\\n")
                elif in_string and char == "\r":
                    result.append("\\r")
                elif in_string and char == "\t":
                    result.append("\\t")
                else:
                    result.append(char)

            return "".join(result)

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
            "messages": [{"role": "user", "content": prompt}],
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
            console.print("[red][ARCHITECT] Unexpected response format[/red]")
            raise ArchitectError(f"Unexpected Bedrock response: {e}") from e

        # Clean and parse JSON
        try:
            clean_json = self._clean_json(raw_text)
            manifest_data = json.loads(clean_json)
        except json.JSONDecodeError as e:
            console.print("[red][ARCHITECT] JSON parsing failed[/red]")
            raise ArchitectError(f"Invalid JSON: {e}") from e

        # Validate with Pydantic
        try:
            manifest = GantryManifest(**manifest_data)
            console.print(f"[green][ARCHITECT] Blueprint ready: {manifest.project_name}[/green]")
            return manifest
        except ValidationError as e:
            console.print("[red][ARCHITECT] Manifest validation failed[/red]")
            raise ArchitectError(f"Manifest validation failed: {e}") from e

    def heal_blueprint(self, original_manifest: GantryManifest, error_log: str) -> GantryManifest:
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
        console.print("[yellow][ARCHITECT] Self-healing: analyzing failure...[/yellow]")

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
            "messages": [{"role": "user", "content": healing_request}],
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
            console.print("[red][ARCHITECT] Unexpected healing response[/red]")
            raise ArchitectError(f"Unexpected response: {e}") from e

        # Clean and parse JSON
        try:
            clean_json = self._clean_json(raw_text)
            manifest_data = json.loads(clean_json)
        except json.JSONDecodeError as e:
            console.print("[red][ARCHITECT] Healing JSON parse failed[/red]")
            raise ArchitectError(f"Invalid healing JSON: {e}") from e

        # Validate with Pydantic
        try:
            healed_manifest = GantryManifest(**manifest_data)
            console.print(
                f"[green][ARCHITECT] Healed blueprint ready: {healed_manifest.project_name}[/green]"
            )
            return healed_manifest
        except ValidationError as e:
            console.print("[red][ARCHITECT] Healed manifest validation failed[/red]")
            raise ArchitectError(f"Healed manifest invalid: {e}") from e

    def consult(self, messages: list[dict]) -> dict:
        """
        Architectural consultation - have a conversation about the project.

        This is the "Critic" skill that reviews requirements before building.
        The Architect answers questions about scalability, testing, security, etc.

        Args:
            messages: Conversation history [{"role": "user"|"assistant", "content": "..."}]

        Returns:
            dict with response, ready_to_build, suggested_stack, etc.
        """
        console.print("[cyan][ARCHITECT] Consulting on architecture...[/cyan]")

        url = f"{self._endpoint}/model/{CLAUDE_MODEL_ID}/invoke"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": CONSULT_PROMPT,
            "messages": messages,
        }

        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)

            if response.status_code != 200:
                console.print(f"[red][ARCHITECT] Consult API error: {response.status_code}[/red]")
                return {
                    "response": "I'm having trouble connecting. Please try again.",
                    "ready_to_build": False,
                }

            response_body = response.json()
            raw_text = response_body["content"][0]["text"]

            # Try to parse as JSON
            try:
                clean_json = self._clean_json(raw_text)
                result = json.loads(clean_json)

                # Handle case where Claude double-encoded JSON in the response field
                resp_field = result.get("response", "")
                if isinstance(resp_field, str) and resp_field.strip().startswith("{"):
                    console.print("[cyan][ARCHITECT] Detected nested JSON, extracting...[/cyan]")
                    try:
                        inner = json.loads(resp_field)
                        if isinstance(inner, dict) and "response" in inner:
                            result = inner  # Use the inner JSON
                            console.print(
                                "[green][ARCHITECT] Successfully extracted inner JSON[/green]"
                            )
                    except json.JSONDecodeError as e:
                        console.print(f"[yellow][ARCHITECT] Inner JSON parse failed: {e}[/yellow]")

                console.print(
                    f"[green][ARCHITECT] Consultation complete (ready: {result.get('ready_to_build', False)})[/green]"
                )
                return result
            except (json.JSONDecodeError, ArchitectError) as e:
                console.print(
                    f"[yellow][ARCHITECT] JSON parse failed: {e}, returning raw text[/yellow]"
                )
                return {"response": raw_text, "ready_to_build": False}

        except requests.RequestException as e:
            console.print(f"[red][ARCHITECT] Consult request failed: {e}[/red]")
            return {"response": f"Connection error: {e}", "ready_to_build": False}
