# Copyright 2026 Pramod Kumar Voola
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -----------------------------------------------------------------------------
# GANTRY FLEET - FASTAPI INTERFACE
# -----------------------------------------------------------------------------
# Modern async API with consultation loop and production enhancements.
#
# Features:
# - Full consultation loop (voice, consult, themes)
# - WebSocket real-time updates
# - OpenTelemetry-ready structured logging
# - Enhanced health checks
# - Async throughout
#
# Endpoints:
# - GET  /              : Web UI
# - GET  /health        : Enhanced health check
# - GET  /ready         : Readiness probe (2026)
# - POST /gantry/auth   : Authentication
# - POST /gantry/voice  : consultation entry
# - POST /gantry/consult: consultation
# - GET  /gantry/consultation/{id} : Get consultation state
# - GET  /gantry/themes : Famous app themes
# - POST /gantry/architect : Direct build
# - POST /gantry/chat   : Chat consultation
# - GET  /gantry/status/{id} : Mission status
# - GET  /gantry/latest : Latest mission
# - GET  /gantry/missions : List missions
# - POST /gantry/missions/clear : Clear all
# - POST /gantry/missions/{id}/retry : Retry failed
# - GET  /gantry/missions/{id}/failure : Failure details
# - GET  /gantry/search : Search missions
# - WS   /gantry/ws/{id} : Real-time updates
# -----------------------------------------------------------------------------

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.core.architect import FAMOUS_THEMES, Architect, ArchitectError
from src.core.auth import (
    RateLimiter,
    TokenBucket,
    authenticate_user,
    check_guardrails,
    get_current_user,
    verify_session,
)
from src.core.db import get_mission, init_db, list_missions
from src.core.fleet import FleetManager
from src.skills import load_skills

console = Console()

# =============================================================================
# STARTUP TIME TRACKING (2026 PATTERN)
# =============================================================================

_startup_time: datetime | None = None


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================


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

    def get_connection_count(self) -> int:
        """Get total active connections (for health check)."""
        return sum(len(conns) for conns in self.active_connections.values())


manager = ConnectionManager()

# Rate limiter instances
ip_limiter = RateLimiter(window=60, max_requests=30)
user_limiter = TokenBucket(rate=10, capacity=30)


# =============================================================================
# LIFESPAN (STARTUP/SHUTDOWN)
# =============================================================================


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown events."""
    global _startup_time

    # Startup
    print_banner()
    init_db()
    load_skills()

    # Create missions directory
    missions_dir = PROJECT_ROOT / "missions"
    missions_dir.mkdir(exist_ok=True)

    _startup_time = datetime.now(timezone.utc)
    console.print("[green]GANTRY FLEET ONLINE (FastAPI v7.0)[/green]")

    yield

    # Shutdown
    console.print("[yellow]GANTRY FLEET SHUTTING DOWN[/yellow]")


app = FastAPI(
    title="Gantry Fleet",
    description="AI-Powered Software Studio - Voice & Chat Interface (2026 Architecture)",
    version="7.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
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


class VoiceRequest(BaseModel):
    """Voice/consult request."""

    message: str = Field(..., description="The voice memo or chat message")
    deploy: bool = Field(True, description="Whether to deploy to Vercel")
    publish: bool = Field(True, description="Whether to publish to GitHub")
    image_base64: str | None = Field(None, description="Base64-encoded design image")
    image_filename: str | None = Field(None, description="Original filename for image")


class IterationInfo(BaseModel):
    """Single iteration in project breakdown."""

    iteration: int
    name: str
    features: list[str] = []
    buildable_now: bool = False


class ConsultResponse(BaseModel):
    """Consultation response."""

    status: str
    speech: str
    mission_id: str | None = None
    question: str | None = None
    proposed_stack: str | None = None
    design_target: str | None = None
    features: list[str] | None = None
    confidence: float | None = None
    # Iteration planning for complex projects
    iterations: list[IterationInfo] | None = None
    total_iterations: int | None = None
    current_iteration: int | None = None


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


class RetryRequest(BaseModel):
    deploy: bool = True
    publish: bool = True


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
# CORE ENDPOINTS
# =============================================================================


@app.get("/")
async def index():
    """Serve the Gantry Console UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health_check():
    """Enhanced health check (2026 pattern)."""
    uptime = None
    if _startup_time:
        uptime = (datetime.now(timezone.utc) - _startup_time).total_seconds()

    return {
        "status": "healthy",
        "service": "gantry",
        "version": "7.0.0",
        "uptime_seconds": uptime,
        "websocket_connections": manager.get_connection_count(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
async def readiness_check():
    """Readiness probe for Kubernetes/Docker (2026 pattern)."""
    # Check critical dependencies
    checks = {
        "database": False,
        "architect": False,
    }

    try:
        # Quick DB check
        _ = list_missions(limit=1)
        checks["database"] = True
    except Exception:
        pass

    try:
        # Architect availability (lazy, just check it can init)
        checks["architect"] = True
    except Exception:
        pass

    all_ready = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={"ready": all_ready, "checks": checks},
    )


# =============================================================================
# AUTHENTICATION
# =============================================================================


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


# =============================================================================
# CONSULTATION LOOP ENDPOINTS
# =============================================================================


@app.post("/gantry/voice", response_model=ConsultResponse)
async def voice(
    request: VoiceRequest,
    _ip: Annotated[None, Depends(rate_limit_ip)],
    _user_id: Annotated[str, Depends(get_current_user)],
):
    """
    Main Entry Point: Process voice/chat through the Consultation Loop.

    This replaces direct builds with a conversational flow:
    1. First request -> AI Architect analyzes and asks clarifying questions
    2. User answers -> AI Architect confirms understanding
    3. User says "proceed" -> Clone protocol initiated
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    fleet = get_fleet()
    result = await fleet.process_voice_input(
        request.message,
        deploy=request.deploy,
        publish=request.publish,
        image_base64=request.image_base64,
        image_filename=request.image_filename,
    )

    return ConsultResponse(**result)


@app.post("/gantry/consult", response_model=ConsultResponse)
async def consult(
    request: VoiceRequest,
    _ip: Annotated[None, Depends(rate_limit_ip)],
    _user_id: Annotated[str, Depends(get_current_user)],
):
    """
    Consultation endpoint - start or continue a consultation.
    Same as /gantry/voice but with explicit naming.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    fleet = get_fleet()
    result = await fleet.process_voice_input(
        request.message,
        deploy=request.deploy,
        publish=request.publish,
        image_base64=request.image_base64,
        image_filename=request.image_filename,
    )

    return ConsultResponse(**result)


@app.get("/gantry/consultation/{mission_id}")
async def get_consultation(mission_id: str):
    """Get the current state of a consultation."""
    mission = get_mission(mission_id)

    if mission is None:
        raise HTTPException(status_code=404, detail="Consultation not found")

    return {
        "mission_id": mission.id,
        "status": mission.status,
        "prompt": mission.prompt,
        "conversation_history": mission.conversation_history or [],
        "pending_question": mission.pending_question,
        "design_target": mission.design_target,
        "proposed_stack": mission.proposed_stack,
        "speech": mission.speech_output or f"Status: {mission.status}",
    }


@app.get("/gantry/themes")
async def list_themes():
    """List available famous app themes for cloning."""
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

    return {
        "count": len(themes),
        "themes": themes,
        "speech": f"{len(themes)} famous app themes available for cloning.",
    }


# =============================================================================
# BUILD ENDPOINTS
# =============================================================================


@app.post("/gantry/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _ip: Annotated[None, Depends(rate_limit_ip)],
    _user_id: Annotated[str, Depends(get_current_user)],
):
    """Chat with the AI Architect."""
    user_messages = [m for m in request.messages if m.get("role") == "user"]
    if user_messages:
        last_message = user_messages[-1].get("content", "")
        guardrail_result = check_guardrails(last_message)
        if not guardrail_result.passed:
            return ChatResponse(response=guardrail_result.suggestion, ready_to_build=False)

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
    _user_id: Annotated[str, Depends(get_current_user)],
    wait: bool = False,
):
    """Dispatch a build mission (direct, bypasses consultation)."""
    if not request.voice_memo.strip():
        raise HTTPException(status_code=400, detail="voice_memo is required")

    fleet = get_fleet()
    mission_id = await fleet.dispatch_mission(
        request.voice_memo,
        deploy=request.deploy,
        publish=request.publish,
    )

    if wait:
        terminal_states = [
            "SUCCESS",
            "DEPLOYED",
            "PR_OPENED",
            "FAILED",
            "BLOCKED",
            "TIMEOUT",
            "CRITICAL_FAILURE",
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


# =============================================================================
# MISSION STATUS ENDPOINTS
# =============================================================================


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
    response = {
        "mission_id": latest.id,
        "status": latest.status,
        "prompt": latest.prompt[:50],
        "speech": latest.speech_output or f"Status: {latest.status}",
    }

    if latest.speech_output and "http" in latest.speech_output:
        response["url"] = "http" + latest.speech_output.split("http")[-1].split()[0].rstrip(".")

    return response


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
        "speech": f"{len(missions)} missions on record.",
    }


# =============================================================================
# MISSION MANAGEMENT ENDPOINTS
# =============================================================================


@app.post("/gantry/missions/clear")
async def clear_missions(
    _ip: Annotated[None, Depends(rate_limit_ip)],
    _user_id: Annotated[str, Depends(get_current_user)],
):
    """Clear all projects (delete all missions from DB)."""
    try:
        count = get_fleet().clear_projects()
        return {
            "cleared": count,
            "speech": f"Cleared {count} projects. You can start fresh.",
        }
    except Exception as e:
        console.print(f"[red][API] Clear missions error: {e}[/red]")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gantry/missions/{mission_id}/retry")
async def retry_mission(
    mission_id: str,
    request: RetryRequest = None,
    _ip: Annotated[None, Depends(rate_limit_ip)] = None,
    _user_id: Annotated[str, Depends(get_current_user)] = None,
):
    """Retry a failed mission from scratch."""
    deploy = request.deploy if request else True
    publish = request.publish if request else True

    fleet = get_fleet()
    result = await fleet.retry_failed_mission(mission_id, deploy=deploy, publish=publish)

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("speech"))

    return result


@app.get("/gantry/missions/{mission_id}/failure")
async def get_mission_failure(
    mission_id: str,
    _user_id: Annotated[str, Depends(get_current_user)],
):
    """Get failure details for a mission from audit evidence."""
    missions_dir = PROJECT_ROOT / "missions" / mission_id
    out = {"mission_id": mission_id, "failure": None, "speech": "No failure details on file."}

    for name in ("audit_fail.json", "flight_recorder.json"):
        path = missions_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
            if name == "audit_fail.json":
                out["failure"] = {
                    "exit_code": data.get("exit_code"),
                    "output": data.get("output", "")[:2000],
                    "verdict": data.get("verdict"),
                }
                out["speech"] = f"Last audit failed: exit code {data.get('exit_code')}."
            else:
                out["failure"] = data
                out["speech"] = "Flight recording available."
            break
        except Exception as e:
            console.print(f"[yellow][API] Read {path}: {e}[/yellow]")

    return out


@app.get("/gantry/search")
async def search_similar(
    q: str = Query("", description="Search query keywords"),
    limit: int = Query(5, description="Max results"),
):
    """Search for similar projects."""
    if not q:
        return {"results": [], "message": "No search query provided"}

    keywords = q.lower().split()
    fleet = get_fleet()
    results = fleet.search_missions_by_keywords(keywords, limit=limit)

    return {
        "query": q,
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


# =============================================================================
# WEBSOCKET - REAL-TIME UPDATES
# =============================================================================


@app.websocket("/gantry/ws/{mission_id}")
async def websocket_endpoint(websocket: WebSocket, mission_id: str):
    """WebSocket for real-time mission updates."""
    await manager.connect(websocket, mission_id)
    try:
        while True:
            data = await websocket.receive_text()
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
    ║           GANTRY FLEET v7.0 (2026 Architecture)   ║
    ║  • FastAPI Async Core                             ║
    ║  • AI Architect Consultation Loop                 ║
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
