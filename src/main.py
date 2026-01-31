# -----------------------------------------------------------------------------
# GANTRY FLEET - API INTERFACE
# -----------------------------------------------------------------------------
# Responsibility: The endpoint for voice-activated commands.
# Designed for iOS Shortcuts and TTS engines.
#
# Endpoints:
# - POST /gantry/architect: Accept voice memo, dispatch mission
# - GET /gantry/status/<id>: Get mission status and speech
# -----------------------------------------------------------------------------

import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from flask import Flask, request, jsonify
from rich.console import Console
from rich.panel import Panel

from src.core.fleet import FleetManager
from src.core.db import get_mission, list_missions, init_db

console = Console()
app = Flask(__name__)

# Global Fleet Manager (lazy init)
fleet: Optional[FleetManager] = None


def get_fleet() -> FleetManager:
    """Get or initialize the Fleet Manager."""
    global fleet
    if fleet is None:
        fleet = FleetManager()
    return fleet


@app.route("/health", methods=["GET"])
def health_check():
    """Health check for Docker and load balancers."""
    return jsonify({
        "status": "online",
        "service": "gantry",
        "speech": "Gantry Fleet online and ready."
    })


@app.route("/gantry/architect", methods=["POST"])
def architect():
    """
    Main endpoint for voice commands.
    
    Input: {"voice_memo": "Build me a Flask API"}
    Output: 202 with {"status": "queued", "speech": "Copy. Gantry assumes control."}
    """
    try:
        data = request.json
        if not data:
            return jsonify({
                "status": "error",
                "error": "No JSON payload",
                "speech": "Error. No data received."
            }), 400
        
        voice_memo = data.get("voice_memo", "").strip()
        if not voice_memo:
            return jsonify({
                "status": "error",
                "error": "Missing voice_memo field",
                "speech": "Error. No voice memo provided."
            }), 400
        
        console.print(f"[cyan][API] Voice memo: {voice_memo[:50]}...[/cyan]")
        
        # Dispatch to Fleet
        mission_id = get_fleet().dispatch_mission(voice_memo)
        
        return jsonify({
            "status": "queued",
            "mission_id": mission_id,
            "speech": "Copy. Gantry assumes control."
        }), 202
        
    except Exception as e:
        console.print(f"[red][API] Error: {e}[/red]")
        return jsonify({
            "status": "error",
            "error": str(e),
            "speech": "System error. Please try again."
        }), 500


@app.route("/gantry/status/<mission_id>", methods=["GET"])
def get_status(mission_id: str):
    """
    Get mission status and speech for TTS.
    
    Designed for polling from iOS Shortcuts.
    """
    mission = get_mission(mission_id)
    
    if mission is None:
        return jsonify({
            "status": "not_found",
            "error": "Mission not found",
            "speech": "Mission not found."
        }), 404
    
    return jsonify({
        "mission_id": mission.id,
        "status": mission.status,
        "created_at": mission.created_at,
        "speech": mission.speech_output or f"Status: {mission.status}"
    })


@app.route("/gantry/missions", methods=["GET"])
def list_all_missions():
    """List recent missions."""
    missions = list_missions(limit=20)
    
    return jsonify({
        "count": len(missions),
        "missions": [
            {
                "mission_id": m.id,
                "status": m.status,
                "prompt": m.prompt[:50] + "..." if len(m.prompt) > 50 else m.prompt,
            }
            for m in missions
        ],
        "speech": f"{len(missions)} missions on record."
    })


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
    ║  • Voice-Activated Software Factory               ║
    ║  • Zero-Trust Build Pipeline                      ║
    ║  • Dead Man's Switch (180s TTL)                   ║
    ╚═══════════════════════════════════════════════════╝
    """
    console.print(Panel(banner, border_style="cyan"))


if __name__ == "__main__":
    print_banner()
    
    # Ensure missions directory exists
    missions_dir = PROJECT_ROOT / "missions"
    missions_dir.mkdir(exist_ok=True)
    
    port = int(os.getenv("GANTRY_PORT", 5050))
    console.print(f"[green]GANTRY FLEET ONLINE[/green] - Port {port}")
    console.print("[dim]POST /gantry/architect | GET /gantry/status/<id>[/dim]")
    
    app.run(host="0.0.0.0", port=port)
