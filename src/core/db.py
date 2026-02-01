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
# MISSION DATABASE (PostgreSQL)
# -----------------------------------------------------------------------------
# Responsibility: Persistent storage for mission tracking using PostgreSQL
# with connection pooling for efficiency and reliability.
#
# Why PostgreSQL over SQLite:
# - Connection pooling for concurrent access
# - Better for containerized deployments
# - Supports distributed setups if needed
# -----------------------------------------------------------------------------

import os
import uuid
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from pydantic import BaseModel
from rich.console import Console

console = Console()

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "gantry"),
    "password": os.getenv("DB_PASSWORD", "securepass"),
    "database": os.getenv("DB_NAME", "gantry_fleet"),
    # Connection and query timeouts to prevent pool exhaustion
    "connect_timeout": 10,  # 10s connection timeout
    "options": "-c statement_timeout=30000",  # 30s query timeout (in ms)
}

# Connection pool (initialized on first use)
_pool: SimpleConnectionPool | None = None


class MissionRecord(BaseModel):
    """
    Pydantic model for a mission database record.

    Why Pydantic: Type safety and validation when reading from DB.

    Consultation Additions:
    - conversation_history: Tracks the back-and-forth with user
    - design_target: Famous app being cloned (LINKEDIN, TWITTER, etc.)
    - pending_question: Question waiting for user response
    """

    id: str
    prompt: str
    status: str
    speech_output: str | None = None
    created_at: str
    updated_at: str | None = None
    # Consultation Loop Fields
    conversation_history: list[dict] | None = None
    design_target: str | None = None
    pending_question: str | None = None
    proposed_stack: str | None = None


def _get_pool() -> SimpleConnectionPool:
    """
    Get or create the connection pool.

    Why connection pooling: Reuses connections instead of creating new ones,
    improving performance and reducing database load.

    Connection and query timeouts prevent pool exhaustion under load.
    """
    global _pool

    if _pool is None:
        try:
            _pool = SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=DB_CONFIG["host"],
                port=DB_CONFIG["port"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                database=DB_CONFIG["database"],
                connect_timeout=DB_CONFIG["connect_timeout"],
                options=DB_CONFIG["options"],
            )
            console.print(
                f"[green][DB] Connection pool created: {DB_CONFIG['host']}:{DB_CONFIG['port']} "
                f"(timeout: {DB_CONFIG['connect_timeout']}s)[/green]"
            )
        except psycopg2.Error as e:
            console.print(f"[red][DB] Failed to create connection pool: {e}[/red]")
            raise

    return _pool


@contextmanager
def get_connection():
    """
    Context manager for database connections from the pool.

    Why context manager: Ensures connections are returned to the pool,
    even if an exception occurs.
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_db() -> None:
    """
    Initialize the missions database table.

    Why explicit init: Ensures table exists before any operations.
    Called at application startup. Safe to call multiple times.

    Added conversation_history, design_target, pending_question columns.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id UUID PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                    speech_output TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    conversation_history JSONB DEFAULT '[]'::jsonb,
                    design_target VARCHAR(100),
                    pending_question TEXT,
                    proposed_stack VARCHAR(50)
                )
            """)

        # Create index for faster status queries
        cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_missions_status 
                ON missions(status)
            """)

        # Create index for faster created_at queries (for listing)
        cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_missions_created_at 
                ON missions(created_at DESC)
            """)

        # Add new columns if they don't exist (migration for existing DBs)
        for column, col_type in [
            ("conversation_history", "JSONB DEFAULT '[]'::jsonb"),
            ("design_target", "VARCHAR(100)"),
            ("pending_question", "TEXT"),
            ("proposed_stack", "VARCHAR(50)"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE missions ADD COLUMN IF NOT EXISTS {column} {col_type}")
            except Exception:
                pass  # Column already exists

    console.print(f"[green][DB] Database initialized: {DB_CONFIG['database']}[/green]")


def create_mission(prompt: str) -> str:
    """
    Create a new mission record.

    Args:
        prompt: The user's voice command / build request.

    Returns:
        The generated mission ID (UUID).
    """
    mission_id = str(uuid.uuid4())

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO missions (id, prompt, status, created_at)
                VALUES (%s, %s, 'PENDING', CURRENT_TIMESTAMP)
                """,
            (mission_id, prompt),
        )

    console.print(f"[cyan][DB] Mission created: {mission_id[:8]}[/cyan]")
    return mission_id


def update_mission_status(mission_id: str, status: str, speech: str | None = None) -> None:
    """
    Update the status and speech output of a mission.

    Args:
        mission_id: The UUID of the mission.
        status: New status (PENDING, BUILDING, SUCCESS, FAILED, TIMEOUT).
        speech: Optional speech output for TTS.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE missions 
                SET status = %s, speech_output = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
            (status, speech, mission_id),
        )

    console.print(f"[cyan][DB] Mission {mission_id[:8]} -> {status}[/cyan]")


def get_mission(mission_id: str) -> MissionRecord | None:
    """
    Retrieve a mission by ID.

    Args:
        mission_id: The UUID of the mission.

    Returns:
        MissionRecord if found, None otherwise.
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM missions WHERE id = %s", (mission_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return MissionRecord(
            id=str(row["id"]),
            prompt=row["prompt"],
            status=row["status"],
            speech_output=row["speech_output"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
            # Consultation fields
            conversation_history=row.get("conversation_history") or [],
            design_target=row.get("design_target"),
            pending_question=row.get("pending_question"),
            proposed_stack=row.get("proposed_stack"),
        )


def list_missions(limit: int = 50) -> list[MissionRecord]:
    """
    List recent missions.

    Args:
        limit: Maximum number of missions to return.

    Returns:
        List of MissionRecord objects, most recent first.
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM missions 
                ORDER BY created_at DESC 
                LIMIT %s
                """,
            (limit,),
        )
        rows = cursor.fetchall()

        return [
            MissionRecord(
                id=str(row["id"]),
                prompt=row["prompt"],
                status=row["status"],
                speech_output=row["speech_output"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                # Consultation fields
                conversation_history=row.get("conversation_history") or [],
                design_target=row.get("design_target"),
                pending_question=row.get("pending_question"),
                proposed_stack=row.get("proposed_stack"),
            )
            for row in rows
        ]


def search_missions(keywords: list[str], limit: int = 5) -> list[MissionRecord]:
    """
    Search for missions containing any of the keywords.

    Used for the resume/continue feature to find similar apps.

    Args:
        keywords: List of keywords to search for in prompt.
        limit: Maximum number of missions to return.

    Returns:
        List of matching MissionRecord objects.
    """
    if not keywords:
        return []

    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Build ILIKE conditions for each keyword
        conditions = " OR ".join(["prompt ILIKE %s" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]
        params.append(limit)

        cursor.execute(
            f"""
                SELECT * FROM missions 
                WHERE status = 'DEPLOYED' AND ({conditions})
                ORDER BY created_at DESC 
                LIMIT %s
                """,
            params,
        )
        rows = cursor.fetchall()

        return [
            MissionRecord(
                id=str(row["id"]),
                prompt=row["prompt"],
                status=row["status"],
                speech_output=row["speech_output"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
            )
            for row in rows
        ]


def find_missions_by_prompt_hint(hint: str, limit: int = 10) -> list[MissionRecord]:
    """
    Find missions whose prompt matches the hint (any status).

    Used for status queries: e.g. "status of linkedin website" -> hint "linkedin website".

    Args:
        hint: Substring to search for in prompt (ILIKE).
        limit: Maximum number of missions to return.

    Returns:
        List of MissionRecord objects, most recent first.
    """
    if not hint or not hint.strip():
        return []

    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM missions
                WHERE prompt ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
            (f"%{hint.strip()}%", limit),
        )
        rows = cursor.fetchall()

        return [
            MissionRecord(
                id=str(row["id"]),
                prompt=row["prompt"],
                status=row["status"],
                speech_output=row["speech_output"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                conversation_history=row.get("conversation_history") or [],
                design_target=row.get("design_target"),
                pending_question=row.get("pending_question"),
                proposed_stack=row.get("proposed_stack"),
            )
            for row in rows
        ]


def get_mission_by_name(project_name: str) -> MissionRecord | None:
    """
    Get mission by project name (extracted from prompt).

    Args:
        project_name: The project name to search for.

    Returns:
        MissionRecord if found, None otherwise.
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM missions 
                WHERE prompt ILIKE %s AND status = 'DEPLOYED'
                ORDER BY created_at DESC 
                LIMIT 1
                """,
            (f"%{project_name}%",),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return MissionRecord(
            id=str(row["id"]),
            prompt=row["prompt"],
            status=row["status"],
            speech_output=row["speech_output"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        )


def clear_all_missions() -> int:
    """
    Delete all missions from the database (clear projects list).

    Use with caution: this cannot be undone. Mission folders under missions/
    are left on disk for audit trail; only DB rows are removed.

    Returns:
        Number of missions deleted.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM missions")
        count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM missions")
    console.print(f"[cyan][DB] Cleared {count} missions[/cyan]")
    return count


def close_pool() -> None:
    """
    Close all connections in the pool.

    Call this on application shutdown for clean cleanup.
    """
    global _pool

    if _pool is not None:
        _pool.closeall()
        _pool = None
        console.print("[cyan][DB] Connection pool closed[/cyan]")


# =============================================================================
# CONSULTATION LOOP DATABASE METHODS
# =============================================================================


def create_consultation(prompt: str, design_target: str | None = None) -> str:
    """
    Create a new consultation session.

    This is the "Consultation Phase" - before building, we consult.

    Args:
        prompt: The user's initial request.
        design_target: Optional famous app to clone (LINKEDIN, TWITTER, etc.)

    Returns:
        The consultation/mission ID.
    """
    import json

    mission_id = str(uuid.uuid4())
    initial_history = [{"role": "user", "content": prompt}]

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO missions (id, prompt, status, conversation_history, design_target, created_at)
            VALUES (%s, %s, 'CONSULTING', %s, %s, CURRENT_TIMESTAMP)
            """,
            (mission_id, prompt, json.dumps(initial_history), design_target),
        )

    console.print(f"[cyan][DB] Consultation started: {mission_id[:8]}[/cyan]")
    return mission_id


def append_to_conversation(mission_id: str, role: str, content: str) -> None:
    """
    Append a message to the conversation history.

    Args:
        mission_id: The mission/consultation ID.
        role: 'user' or 'assistant'.
        content: The message content.
    """
    import json

    with get_connection() as conn, conn.cursor() as cursor:
        # Fetch current history
        cursor.execute("SELECT conversation_history FROM missions WHERE id = %s", (mission_id,))
        row = cursor.fetchone()
        history = row[0] if row and row[0] else []

        # Append new message
        history.append({"role": role, "content": content})

        # Update
        cursor.execute(
            """
            UPDATE missions 
            SET conversation_history = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (json.dumps(history), mission_id),
        )

    console.print(f"[dim][DB] Conversation updated: {mission_id[:8]} (+{role})[/dim]")


def set_pending_question(mission_id: str, question: str, proposed_stack: str | None = None) -> None:
    """
    Set a pending question that Gantry is waiting for the user to answer.

    Args:
        mission_id: The mission/consultation ID.
        question: The question to ask the user.
        proposed_stack: Optional proposed tech stack.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE missions 
            SET pending_question = %s, proposed_stack = %s, 
                status = 'AWAITING_INPUT', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (question, proposed_stack, mission_id),
        )

    console.print(f"[yellow][DB] Awaiting input: {mission_id[:8]}[/yellow]")


def clear_pending_question(mission_id: str) -> None:
    """
    Clear the pending question after user responds.

    Args:
        mission_id: The mission/consultation ID.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE missions 
            SET pending_question = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (mission_id,),
        )


def set_design_target(mission_id: str, design_target: str) -> None:
    """
    Set the design target (famous app to clone).

    Args:
        mission_id: The mission/consultation ID.
        design_target: The design target (LINKEDIN, TWITTER, etc.)
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE missions 
            SET design_target = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (design_target.upper(), mission_id),
        )

    console.print(f"[cyan][DB] Design target set: {design_target}[/cyan]")


def get_active_consultation(limit: int = 1) -> MissionRecord | None:
    """
    Get the most recent active consultation (CONSULTING or AWAITING_INPUT).

    Used to check if there's an ongoing conversation to continue.

    Args:
        limit: Number of consultations to return.

    Returns:
        MissionRecord if found, None otherwise.
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT * FROM missions 
            WHERE status IN ('CONSULTING', 'AWAITING_INPUT')
            ORDER BY created_at DESC 
            LIMIT %s
            """,
            (limit,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return MissionRecord(
            id=str(row["id"]),
            prompt=row["prompt"],
            status=row["status"],
            speech_output=row["speech_output"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
            conversation_history=row.get("conversation_history") or [],
            design_target=row.get("design_target"),
            pending_question=row.get("pending_question"),
            proposed_stack=row.get("proposed_stack"),
        )


def mark_ready_to_build(mission_id: str) -> None:
    """
    Mark consultation as ready to build.

    Called when user confirms "proceed" or "yes".

    Args:
        mission_id: The mission/consultation ID.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE missions 
            SET status = 'READY_TO_BUILD', pending_question = NULL, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (mission_id,),
        )

    console.print(f"[green][DB] Ready to build: {mission_id[:8]}[/green]")
