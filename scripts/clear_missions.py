#!/usr/bin/env python3
"""
Clear all missions from the database (Projects list).

Use when:
- The UI "Clear all" doesn't work (e.g. auth/session issue).
- You want to reset the Projects list from the command line.
- You need to verify the DB is empty after clearing.

Run from project root:
  python scripts/clear_missions.py
  # or
  python -m scripts.clear_missions

Requires: PostgreSQL running and DB env vars (DB_HOST, DB_NAME, etc.) or .env.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.db import init_db, clear_all_missions

if __name__ == "__main__":
    init_db()
    n = clear_all_missions()
    print(f"Cleared {n} missions from the database. Projects list is now empty.")
