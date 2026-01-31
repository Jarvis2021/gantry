# -----------------------------------------------------------------------------
# GANTRY FLEET - FASTAPI INTERFACE
# -----------------------------------------------------------------------------
# Modern async API with WebSocket support for real-time updates.
#
# Endpoints:
# - GET  /              : Web UI
# - GET  /health        : Health check
# - POST /gantry/auth   : Authentication
# - POST /gantry/chat   : Chat consultation
# - POST /gantry/architect : Build dispatch
# - WS   /gantry/ws     : Real-time updates
# -----------------------------------------------------------------------------

import asyncio
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.core.architect import Architect, ArchitectError
from src.core.auth_v2 import (
    RateLimiter,
    TokenBucket,
    authenticate_user,
    check_guardrails,
    get_current_user,
    verify_session,
)
from src.core.db import get_mission, init_db, list_missions
from src.core.fleet_v2 import FleetManager
from src.skills import load_skills

console = Console()

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, mission_id: str) -> None:
        await websocket.accept()
        if mission_id not in self.active_connections:
            self.active_connections[mission_id] = []
        self.active_connections[mission_id].append(websocket)
        console.print(f"[cyan][WS] Client connected for mission {mission_id[:8]}[/cyan]")

    def disconnect(self, websocket: WebSocket, mission_id: str) -> None:
        if mission_id in self.active_connections:
            if websocket in self.active_connections[mission_id]:
                self.active_connections[mission_id].remove(websocket)
            if not self.active_connections[mission_id]:
                del self.active_connections[mission_id]

    async def broadcast(self, mission_id: str, message: dict) -> None:
        """Broadcast message to all clients watching a mission."""
        if mission_id in self.active_connections:
            for connection in self.active_connections[mission_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()

# Rate limiter instances
ip_limiter = RateLimiter(window=60, max_requests=30)
user_limiter = TokenBucket(rate=10, capacity=30)  # 10 req/sec, burst 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print_banner()
    init_db()
    load_skills()

    # Create missions directory
    missions_dir = PROJECT_ROOT / "missions"
    missions_dir.mkdir(exist_ok=True)

    console.print("[green]GANTRY FLEET ONLINE[/green]")

    yield

    # Shutdown
    console.print("[yellow]GANTRY FLEET SHUTTING DOWN[/yellow]")


app = FastAPI(
    title="Gantry Fleet",
    description="AI-Powered Software Studio - Voice & Chat Interface",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Fleet Manager (lazy init)
_fleet: FleetManager | None = None


def get_fleet() -> FleetManager:
    global _fleet
    if _fleet is None:
        _fleet = FleetManager(ws_manager=manager)
    return _fleet


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class AuthRequest(BaseModel):
    password: str


class AuthResponse(BaseModel):
    authenticated: bool
    speech: str
    token: str | None = None


class ChatRequest(BaseModel):
    messages: list[dict]


class ChatResponse(BaseModel):
    response: str
    ready_to_build: bool
    suggested_stack: str | None = None
    app_name: str | None = None
    key_features: list[str] | None = None


class BuildRequest(BaseModel):
    voice_memo: str
    deploy: bool = True
    publish: bool = True


class BuildResponse(BaseModel):
    status: str
    mission_id: str
    speech: str


class MissionStatus(BaseModel):
    mission_id: str
    status: str
    speech: str | None
    created_at: str | None = None


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================


async def rate_limit_ip(request: Request) -> None:
    """Rate limit by IP address."""
    client_ip = request.client.host if request.client else "unknown"
    if not ip_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before retrying.",
        )


async def rate_limit_user(user_id: str = Depends(get_current_user)) -> None:
    """Rate limit by user ID."""
    if not user_limiter.consume(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="User rate limit exceeded.",
        )


# =============================================================================
# ENDPOINTS
# =============================================================================


@app.get("/")
async def index():
    """Serve the Gantry Console UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health_check():
    """Health check for Docker and load balancers."""
    return {"status": "online", "service": "gantry", "version": "2.0.0"}


@app.post("/gantry/auth", response_model=AuthResponse)
async def auth(
    request: AuthRequest,
    _: Annotated[None, Depends(rate_limit_ip)],
):
    """Authenticate and get session token."""
    result = await authenticate_user(request.password)
    if result.success:
        return AuthResponse(
            authenticated=True,
            speech="Welcome to Gantry Fleet. You are authenticated.",
            token=result.token,
        )
    raise HTTPException(status_code=401, detail="Invalid password")


@app.get("/gantry/auth/status")
async def auth_status(request: Request):
    """Check authentication status."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    is_valid = await verify_session(token)
    return {"authenticated": is_valid}


@app.post("/gantry/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _ip: Annotated[None, Depends(rate_limit_ip)],
    user_id: Annotated[str, Depends(get_current_user)],
):
    """Chat with the AI Architect."""
    # Check guardrails
    user_messages = [m for m in request.messages if m.get("role") == "user"]
    if user_messages:
        last_message = user_messages[-1].get("content", "")
        guardrail_result = check_guardrails(last_message)
        if not guardrail_result.passed:
            return ChatResponse(
                response=guardrail_result.suggestion,
                ready_to_build=False,
            )

    try:
        architect = Architect()
        result = architect.consult(request.messages)

        return ChatResponse(
            response=result.get("response", ""),
            ready_to_build=result.get("ready_to_build", False),
            suggested_stack=result.get("suggested_stack"),
            app_name=result.get("app_name"),
            key_features=result.get("key_features"),
        )
    except ArchitectError as e:
        console.print(f"[red][API] Architect error: {e}[/red]")
        raise HTTPException(status_code=503, detail="Architect unavailable")


@app.post("/gantry/architect", response_model=BuildResponse)
async def architect(
    request: BuildRequest,
    _ip: Annotated[None, Depends(rate_limit_ip)],
    user_id: Annotated[str, Depends(get_current_user)],
    wait: bool = False,
):
    """Dispatch a build mission."""
    if not request.voice_memo.strip():
        raise HTTPException(status_code=400, detail="voice_memo is required")

    fleet = get_fleet()
    mission_id = await fleet.dispatch_mission(
        request.voice_memo,
        deploy=request.deploy,
        publish=request.publish,
    )

    if wait:
        # Wait for completion (up to 120 seconds)
        terminal_states = [
            "SUCCESS", "DEPLOYED", "PR_OPENED",
            "FAILED", "BLOCKED", "TIMEOUT", "CRITICAL_FAILURE",
        ]
        for _ in range(40):  # 40 * 3s = 120s
            await asyncio.sleep(3)
            mission = get_mission(mission_id)
            if mission and mission.status in terminal_states:
                return BuildResponse(
                    status=mission.status,
                    mission_id=mission_id,
                    speech=mission.speech_output or f"Mission {mission.status.lower()}.",
                )

    return BuildResponse(
        status="queued",
        mission_id=mission_id,
        speech="Copy. Gantry assumes control.",
    )


@app.get("/gantry/status/{mission_id}", response_model=MissionStatus)
async def get_status(mission_id: str):
    """Get mission status."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    return MissionStatus(
        mission_id=mission.id,
        status=mission.status,
        speech=mission.speech_output,
        created_at=mission.created_at,
    )


@app.get("/gantry/latest")
async def get_latest():
    """Get latest mission status."""
    missions = list_missions(limit=1)
    if not missions:
        return {"status": "idle", "speech": "No active missions. Gantry standing by."}

    latest = missions[0]
    return {
        "mission_id": latest.id,
        "status": latest.status,
        "prompt": latest.prompt[:50],
        "speech": latest.speech_output or f"Status: {latest.status}",
    }


@app.get("/gantry/missions")
async def list_all_missions():
    """List recent missions."""
    missions = list_missions(limit=20)
    return {
        "count": len(missions),
        "missions": [
            {
                "mission_id": m.id,
                "status": m.status,
                "prompt": m.prompt[:50] + "..." if len(m.prompt) > 50 else m.prompt,
            }
            for m in missions
        ],
    }


# =============================================================================
# WEBSOCKET - REAL-TIME UPDATES
# =============================================================================


@app.websocket("/gantry/ws/{mission_id}")
async def websocket_endpoint(websocket: WebSocket, mission_id: str):
    """WebSocket for real-time mission updates."""
    await manager.connect(websocket, mission_id)
    try:
        while True:
            # Keep connection alive, wait for messages
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, mission_id)


# =============================================================================
# BANNER
# =============================================================================


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
    ║           GANTRY FLEET v2.0 (FastAPI)             ║
    ║  • Async Architecture                             ║
    ║  • WebSocket Real-time Updates                    ║
    ║  • Pluggable Skills System                        ║
    ╚═══════════════════════════════════════════════════╝
    """
    console.print(Panel(banner, border_style="cyan"))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("GANTRY_PORT", "5050"))
    uvicorn.run(app, host="0.0.0.0", port=port)
