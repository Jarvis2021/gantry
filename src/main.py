# Copyright 2024 Pramod Kumar Voola
# Licensed under the Apache License, Version 2.0
"""
GantryFleet CLI Entry Point

Run the GantryFleet AI-powered software factory server.

Usage:
    gantryfleet              # Start server on default port 5050
    gantryfleet --port 8080  # Start server on custom port
    gantryfleet --help       # Show help
"""

import argparse
import os
import sys


def main():
    """Main entry point for gantryfleet CLI."""
    parser = argparse.ArgumentParser(
        prog="gantryfleet",
        description="GantryFleet - AI-Powered Software Factory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gantryfleet                    Start server on port 5050
  gantryfleet --port 8080        Start on custom port
  gantryfleet --host 127.0.0.1   Bind to localhost only

Documentation: https://gantryfleet.ai
GitHub: https://github.com/Jarvis2021/gantry
        """,
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("GANTRY_PORT", "5050")),
        help="Port to run the server on (default: 5050)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()

    try:
        import uvicorn

        from src.main_fastapi import app

        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    🏗️  GANTRYFLEET                            ║
║              AI-Powered Software Factory                      ║
╠═══════════════════════════════════════════════════════════════╣
║  Server: http://{args.host}:{args.port}                       
║  Docs:   http://{args.host}:{args.port}/docs                  
║  Health: http://{args.host}:{args.port}/health                
╚═══════════════════════════════════════════════════════════════╝
        """)

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError as e:
        print(f"Error: Missing dependency - {e}", file=sys.stderr)
        print("Run: pip install gantryfleet[dev]", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down GantryFleet...")
        sys.exit(0)


if __name__ == "__main__":
    main()
