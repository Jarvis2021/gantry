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
from datetime import datetime
from typing import Optional, List

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from rich.console import Console

console = Console()

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "gantry"),
    "password": os.getenv("DB_PASSWORD", "securepass"),
    "database": os.getenv("DB_NAME", "gantry_fleet"),
}

# Connection pool (initialized on first use)
_pool: Optional[SimpleConnectionPool] = None


class MissionRecord(BaseModel):
    """
    Pydantic model for a mission database record.
    
    Why Pydantic: Type safety and validation when reading from DB.
    """
    id: str
    prompt: str
    status: str
    speech_output: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


def _get_pool() -> SimpleConnectionPool:
    """
    Get or create the connection pool.
    
    Why connection pooling: Reuses connections instead of creating new ones,
    improving performance and reducing database load.
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
            )
            console.print(f"[green][DB] Connection pool created: {DB_CONFIG['host']}:{DB_CONFIG['port']}[/green]")
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
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id UUID PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                    speech_output TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP
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
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO missions (id, prompt, status, created_at)
                VALUES (%s, %s, 'PENDING', CURRENT_TIMESTAMP)
                """,
                (mission_id, prompt)
            )
    
    console.print(f"[cyan][DB] Mission created: {mission_id[:8]}[/cyan]")
    return mission_id


def update_mission_status(
    mission_id: str, 
    status: str, 
    speech: Optional[str] = None
) -> None:
    """
    Update the status and speech output of a mission.
    
    Args:
        mission_id: The UUID of the mission.
        status: New status (PENDING, BUILDING, SUCCESS, FAILED, TIMEOUT).
        speech: Optional speech output for TTS.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE missions 
                SET status = %s, speech_output = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (status, speech, mission_id)
            )
    
    console.print(f"[cyan][DB] Mission {mission_id[:8]} -> {status}[/cyan]")


def get_mission(mission_id: str) -> Optional[MissionRecord]:
    """
    Retrieve a mission by ID.
    
    Args:
        mission_id: The UUID of the mission.
        
    Returns:
        MissionRecord if found, None otherwise.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM missions WHERE id = %s",
                (mission_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            return MissionRecord(
                id=str(row["id"]),
                prompt=row["prompt"],
                status=row["status"],
                speech_output=row["speech_output"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None
            )


def list_missions(limit: int = 50) -> List[MissionRecord]:
    """
    List recent missions.
    
    Args:
        limit: Maximum number of missions to return.
        
    Returns:
        List of MissionRecord objects, most recent first.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT * FROM missions 
                ORDER BY created_at DESC 
                LIMIT %s
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            
            return [
                MissionRecord(
                    id=str(row["id"]),
                    prompt=row["prompt"],
                    status=row["status"],
                    speech_output=row["speech_output"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    updated_at=row["updated_at"].isoformat() if row["updated_at"] else None
                )
                for row in rows
            ]


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
