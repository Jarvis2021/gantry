# -----------------------------------------------------------------------------
# GANTRY FLEET - API INTERFACE (V6.5 Consultation Loop)
# -----------------------------------------------------------------------------
# Responsibility: The endpoint for voice-activated and chat-based commands.
# Designed for iOS Shortcuts, TTS engines, and web UI.
#
# V6.5 UPGRADE: Consultation Loop
# Old: Voice -> Build (one-shot)
# New: Voice -> CTO Proposal -> User Feedback -> "Proceed" -> Clone Protocol
#
# New Endpoints:
# - POST /gantry/consult: Start/continue consultation (V6.5)
# - POST /gantry/voice: Process voice input through consultation loop
#
# Existing Endpoints:
# - GET /: Serve the Gantry Console UI
# - POST /gantry/architect: Direct build (legacy, bypasses consultation)
# - POST /gantry/chat: Architectural consultation
# - GET /gantry/status/<id>: Get mission status and speech
# - GET /gantry/missions: List recent missions
# -----------------------------------------------------------------------------

import os
import sys
from pathlib import Path
from datetime import timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from flask import Flask, jsonify, request, send_from_directory
from rich.console import Console
from rich.panel import Panel

from src.core.architect import Architect, ArchitectError
from src.core.auth import (
    authenticate_session,
    is_authenticated,
    require_auth,
    require_guardrails,
    require_rate_limit,
)
from src.core.db import get_mission, init_db, list_missions
from src.core.fleet import FleetManager

console = Console()

# Static folder for UI
STATIC_DIR = Path(__file__).parent / "static"
app = Flask(__name__, static_folder=str(STATIC_DIR))

# Secret key for sessions (use env var in production)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
# Keep session across browser restarts and avoid repetitive login
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# Global Fleet Manager (lazy init)
# Note: Architect is created per-request to avoid naming conflicts with Flask routes
fleet: FleetManager | None = None


def get_fleet() -> FleetManager:
    """Get or initialize the Fleet Manager."""
    global fleet
    if fleet is None:
        fleet = FleetManager()
    return fleet


@app.route("/", methods=["GET"])
def index():
    """Serve the Gantry Console UI."""
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/health", methods=["GET"])
def health_check():
    """Health check for Docker and load balancers."""
    return jsonify(
        {"status": "online", "service": "gantry", "speech": "Gantry Fleet online and ready."}
    )


@app.route("/gantry/auth", methods=["POST"])
@require_rate_limit
def auth():
    """
    Authentication endpoint.
    Input: {"password": "your_password"}
    Output: {"authenticated": true/false}
    """
    data = request.json or {}
    password = data.get("password", "")

    if authenticate_session(password):
        return jsonify(
            {
                "authenticated": True,
                "speech": "Welcome to Gantry Fleet. You are now authenticated.",
            }
        )

    return (
        jsonify(
            {
                "authenticated": False,
                "speech": "Invalid password. Please try again.",
            }
        ),
        401,
    )


@app.route("/gantry/auth/status", methods=["GET"])
def auth_status():
    """Check authentication status."""
    return jsonify({"authenticated": is_authenticated()})


@app.route("/gantry/chat", methods=["POST"])
@require_rate_limit
@require_auth
@require_guardrails
def chat():
    """
    Intelligent architectural consultation endpoint.

    The Architect reviews requirements, answers questions about scalability,
    testing, and security, and only triggers a build when user confirms.

    Input: {"messages": [{"role": "user", "content": "Build me a todo API"}]}
    Output: {"response": "...", "ready_to_build": true/false, ...}
    """
    try:
        data = request.json
        if not data or "messages" not in data:
            return jsonify(
                {"response": "Please provide a messages array.", "ready_to_build": False}
            ), 400

        messages = data.get("messages", [])
        if not messages:
            return jsonify({"response": "No messages provided.", "ready_to_build": False}), 400

        # Create Architect instance directly to avoid any caching issues
        try:
            arch = Architect()
        except ArchitectError as e:
            console.print(f"[red][API] Architect init failed: {e}[/red]")
            return jsonify(
                {
                    "response": "Architect is not available. Please check API key configuration.",
                    "ready_to_build": False,
                }
            ), 503

        result = arch.consult(messages)

        return jsonify(result)

    except Exception as e:
        console.print(f"[red][API] Chat error: {e}[/red]")
        import traceback

        console.print(f"[red]{traceback.format_exc()}[/red]")
        return jsonify({"response": f"Error: {e!s}", "ready_to_build": False}), 500


@app.route("/gantry/architect", methods=["POST"])
@require_rate_limit
@require_auth
def architect():
    """
    Main endpoint for voice commands.

    Input: {"voice_memo": "Build me a Flask API", "publish": true}
    Output: 202 with {"status": "queued", "speech": "Copy. Gantry assumes control."}

    Query params:
      ?wait=true - Wait for completion (up to 120s) and return final result

    Body params:
      voice_memo: The build request (required)
      deploy: Whether to deploy to Vercel (default: true)
      publish: Whether to push to GitHub (default: true)

    For tests/CI, set both deploy and publish to false.
    """
    import time

    try:
        data = request.json
        if not data:
            return jsonify(
                {
                    "status": "error",
                    "error": "No JSON payload",
                    "speech": "Error. No data received.",
                }
            ), 400

        voice_memo = data.get("voice_memo", "").strip()
        if not voice_memo:
            return jsonify(
                {
                    "status": "error",
                    "error": "Missing voice_memo field",
                    "speech": "Error. No voice memo provided.",
                }
            ), 400

        # Default to True for real user requests (voice/chat)
        # Set to False for automated tests
        deploy = data.get("deploy", True)
        publish = data.get("publish", True)

        console.print(
            f"[cyan][API] Voice memo: {voice_memo[:50]}... (deploy={deploy}, publish={publish})[/cyan]"
        )

        # Dispatch to Fleet
        mission_id = get_fleet().dispatch_mission(voice_memo, deploy=deploy, publish=publish)

        # Check if caller wants to wait for completion
        wait_for_result = request.args.get("wait", "").lower() == "true"

        if wait_for_result:
            # Poll for completion (max 120 seconds)
            max_wait = 120
            poll_interval = 3
            waited = 0

            terminal_states = [
                "SUCCESS",
                "DEPLOYED",
                "PR_OPENED",
                "FAILED",
                "BLOCKED",
                "TIMEOUT",
                "CRITICAL_FAILURE",
                "PUBLISH_FAILED",
            ]

            while waited < max_wait:
                time.sleep(poll_interval)
                waited += poll_interval

                mission = get_mission(mission_id)
                if mission and mission.status in terminal_states:
                    is_success = mission.status in ["SUCCESS", "DEPLOYED", "PR_OPENED"]
                    return jsonify(
                        {
                            "status": mission.status,
                            "mission_id": mission_id,
                            "speech": mission.speech_output or f"Mission {mission.status.lower()}.",
                            "success": is_success,
                        }
                    ), 200 if is_success else 500

            # Timeout waiting
            return jsonify(
                {
                    "status": "TIMEOUT",
                    "mission_id": mission_id,
                    "speech": "Build is still running. Check status later.",
                    "success": False,
                }
            ), 202

        # Async mode - return immediately
        return jsonify(
            {
                "status": "queued",
                "mission_id": mission_id,
                "speech": "Copy. Gantry assumes control.",
            }
        ), 202

    except Exception as e:
        console.print(f"[red][API] Error: {e}[/red]")
        return jsonify(
            {"status": "error", "error": str(e), "speech": "System error. Please try again."}
        ), 500


@app.route("/gantry/status/<mission_id>", methods=["GET"])
def get_status(mission_id: str):
    """
    Get mission status and speech for TTS.

    Designed for polling from iOS Shortcuts.
    """
    mission = get_mission(mission_id)

    if mission is None:
        return jsonify(
            {"status": "not_found", "error": "Mission not found", "speech": "Mission not found."}
        ), 404

    return jsonify(
        {
            "mission_id": mission.id,
            "status": mission.status,
            "created_at": mission.created_at,
            "speech": mission.speech_output or f"Status: {mission.status}",
        }
    )


@app.route("/gantry/latest", methods=["GET"])
def get_latest_status():
    """
    Get the latest mission status - perfect for voice status checks.

    Just call GET /gantry/latest and Gantry will tell you what's happening.
    """
    missions = list_missions(limit=1)

    if not missions:
        return jsonify({"status": "idle", "speech": "No active missions. Gantry standing by."})

    latest = missions[0]

    # Build a natural speech response based on status
    status_speech = {
        "pending": f"Mission in queue. Building {latest.prompt[:30]}.",
        "running": f"Currently building. {latest.prompt[:30]}. Stand by.",
        "building": "Code generation in progress. Stand by.",
        "deploying": "Deploying to Vercel. Almost there.",
        "healing": "Build failed. Attempting self-repair.",
        "success": f"Mission complete. {latest.speech_output or 'Deployment successful.'}",
        "failed": f"Mission failed. {latest.speech_output or 'Check logs for details.'}",
    }

    speech = status_speech.get(latest.status, f"Status: {latest.status}")

    # Include URL if available in speech_output
    response = {
        "mission_id": latest.id,
        "status": latest.status,
        "prompt": latest.prompt[:50],
        "speech": speech,
    }

    # Extract URL from speech_output if present
    if latest.speech_output and "http" in latest.speech_output:
        response["url"] = latest.speech_output.split("http")[-1]
        response["url"] = "http" + response["url"].split()[0].rstrip(".")

    return jsonify(response)


@app.route("/gantry/missions", methods=["GET"])
def list_all_missions():
    """List recent missions."""
    missions = list_missions(limit=20)

    return jsonify(
        {
            "count": len(missions),
            "missions": [
                {
                    "mission_id": m.id,
                    "status": m.status,
                    "prompt": m.prompt[:50] + "..." if len(m.prompt) > 50 else m.prompt,
                }
                for m in missions
            ],
            "speech": f"{len(missions)} missions on record.",
        }
    )


@app.route("/gantry/search", methods=["GET"])
def search_similar():
    """
    Search for similar projects (for resume/continue feature).

    Query params:
        q: Search query (keywords)
        limit: Max results (default 5)
    """
    from src.core.db import search_missions

    query = request.args.get("q", "")
    limit = int(request.args.get("limit", "5"))

    if not query:
        return jsonify({"results": [], "message": "No search query provided"})

    # Split query into keywords
    keywords = query.lower().split()

    results = search_missions(keywords, limit=limit)

    return jsonify(
        {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "mission_id": m.id,
                    "prompt": m.prompt,
                    "status": m.status,
                    "created_at": m.created_at,
                }
                for m in results
            ],
        }
    )


# =============================================================================
# V6.5: CONSULTATION LOOP ENDPOINTS
# =============================================================================


@app.route("/gantry/voice", methods=["POST"])
@require_rate_limit
@require_auth
def voice():
    """
    V6.5 Main Entry Point: Process voice/chat through the Consultation Loop.

    This replaces direct builds with a conversational flow:
    1. First request -> CTO analyzes and asks clarifying questions
    2. User answers -> CTO confirms understanding
    3. User says "proceed" -> Clone protocol initiated

    Input: {"message": "Build a LinkedIn clone"}
    Output:
    - If needs input: {"status": "AWAITING_INPUT", "speech": "...", "question": "..."}
    - If building: {"status": "BUILDING", "speech": "Clone protocol initiated."}

    Body params:
        message: The voice/chat message (required)
        deploy: Whether to deploy to Vercel (default: true)
        publish: Whether to publish to GitHub (default: true)
    """
    try:
        data = request.json
        if not data:
            return jsonify(
                {
                    "status": "error",
                    "error": "No JSON payload",
                    "speech": "Error. No data received.",
                }
            ), 400

        message = data.get("message", "").strip()
        if not message:
            return jsonify(
                {
                    "status": "error",
                    "error": "Missing message field",
                    "speech": "Error. No message provided.",
                }
            ), 400

        deploy = data.get("deploy", True)
        publish = data.get("publish", True)
        image_base64 = data.get("image_base64")
        image_filename = data.get("image_filename")

        console.print(
            f"[cyan][API] V6.5 Voice: {message[:50]}... "
            f"(deploy={deploy}, publish={publish}, image={bool(image_base64)})[/cyan]"
        )

        # Process through consultation loop (uploaded image saved to mission folder and in repo)
        result = get_fleet().process_voice_input(
            message,
            deploy=deploy,
            publish=publish,
            image_base64=image_base64,
            image_filename=image_filename,
        )

        # Return appropriate status code
        status = result.get("status")
        if status == "BUILDING":
            return jsonify(result), 202  # Accepted, processing
        if status == "error":
            return jsonify(result), 400
        return jsonify(result), 200  # AWAITING_INPUT or other

    except Exception as e:
        console.print(f"[red][API] Voice error: {e}[/red]")
        import traceback

        console.print(f"[red]{traceback.format_exc()}[/red]")
        return jsonify(
            {"status": "error", "error": str(e), "speech": "System error. Try again."}
        ), 500


@app.route("/gantry/consult", methods=["POST"])
@require_rate_limit
@require_auth
def consult():
    """
    V6.5 Consultation endpoint - start or continue a consultation.

    Similar to /gantry/voice but with more detailed response.

    Input: {"message": "Build a LinkedIn clone"}
    Output: {
        "status": "AWAITING_INPUT" | "BUILDING",
        "speech": "I can build a LinkedIn clone. Proceed?",
        "mission_id": "uuid",
        "question": "...",
        "proposed_stack": "next.js",
        "design_target": "LINKEDIN",
        "features": ["Login", "Feed", "Profile"],
        "confidence": 0.85
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "speech": "No data received."}), 400

        message = data.get("message", "").strip()
        if not message:
            return jsonify({"status": "error", "speech": "No message provided."}), 400

        deploy = data.get("deploy", True)
        publish = data.get("publish", True)
        image_base64 = data.get("image_base64")
        image_filename = data.get("image_filename")

        console.print(
            f"[cyan][API] V6.5 Consult: {message[:50]}... (image={bool(image_base64)})[/cyan]"
        )

        result = get_fleet().process_voice_input(
            message,
            deploy=deploy,
            publish=publish,
            image_base64=image_base64,
            image_filename=image_filename,
        )

        return jsonify(result), 202 if result.get("status") == "BUILDING" else 200

    except Exception as e:
        console.print(f"[red][API] Consult error: {e}[/red]")
        return jsonify({"status": "error", "speech": f"Error: {e}"}), 500


@app.route("/gantry/consultation/<mission_id>", methods=["GET"])
def get_consultation(mission_id: str):
    """
    Get the current state of a consultation.

    Returns conversation history, pending question, and design target.
    """
    mission = get_mission(mission_id)

    if mission is None:
        return jsonify({"status": "not_found", "speech": "Consultation not found."}), 404

    return jsonify(
        {
            "mission_id": mission.id,
            "status": mission.status,
            "prompt": mission.prompt,
            "conversation_history": mission.conversation_history or [],
            "pending_question": mission.pending_question,
            "design_target": mission.design_target,
            "proposed_stack": mission.proposed_stack,
            "speech": mission.speech_output or f"Status: {mission.status}",
        }
    )


@app.route("/gantry/themes", methods=["GET"])
def list_themes():
    """
    List available famous app themes for cloning.

    Returns the design system options for the Clone Protocol.
    """
    from src.core.architect import FAMOUS_THEMES

    themes = []
    for key, theme in FAMOUS_THEMES.items():
        themes.append(
            {
                "id": key,
                "name": theme.get("name", key),
                "colors": theme.get("colors", {}),
                "layout": theme.get("layout", ""),
                "sample_page": theme.get("sample_page", ""),
            }
        )

    return jsonify(
        {
            "count": len(themes),
            "themes": themes,
            "speech": f"{len(themes)} famous app themes available for cloning.",
        }
    )


def print_banner() -> None:
    """Print the Gantry startup banner."""
    banner = """
   ██████╗  █████╗ ███╗   ██╗████████╗██████╗ ██╗   ██╗
  ██╔════╝ ██╔══██╗████╗  ██║╚══██╔══╝██╔══██╗╚██╗ ██╔╝
  ██║  ███╗███████║██╔██╗ ██║   ██║   ██████╔╝ ╚████╔╝ 
  ██║   ██║██╔══██║██║╚██╗██║   ██║   ██╔══██╗  ╚██╔╝  
  ╚██████╔╝██║  ██║██║ ╚████║   ██║   ██║  ██║   ██║   
   ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   

    ╔═══════════════════════════════════════════════════╗
    ║           GANTRY FLEET ONLINE                     ║
    ║  • AI-Powered Software Studio                     ║
    ║  • Voice & Chat Interface                         ║
    ║  • Zero-Trust Build Pipeline                      ║
    ╚═══════════════════════════════════════════════════╝
    """
    console.print(Panel(banner, border_style="cyan"))


if __name__ == "__main__":
    print_banner()

    # Initialize database
    init_db()

    # Ensure missions directory exists
    missions_dir = PROJECT_ROOT / "missions"
    missions_dir.mkdir(exist_ok=True)

    port = int(os.getenv("GANTRY_PORT", 5050))
    console.print(f"[green]GANTRY FLEET ONLINE[/green] - Port {port}")
    console.print("[dim]POST /gantry/architect | GET /gantry/status/<id>[/dim]")

    app.run(host="0.0.0.0", port=port)
