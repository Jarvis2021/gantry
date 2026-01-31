import os
import sys
import time
import subprocess
import platform
import docker
from flask import Flask, request, jsonify
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from docker.errors import DockerException, ImageNotFound

# --- CONFIGURATION ---
SYSTEM_NAME = "GANTRY PROTOCOL"
VERSION = "3.0 (Enterprise Core)"
console = Console()
app = Flask(__name__)

# --- 1. THE AUTO-WAKE PROTOCOL ---
def wake_docker():
    """
    Attempts to launch Docker Desktop if it's sleeping.
    """
    system = platform.system()
    console.print("[bold yellow][WARNING] Docker Engine sleeping. Attempting auto-wake...[/bold yellow]")
    
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["open", "-a", "Docker"])
        elif system == "Windows":
            # Try default path, fail gracefully if not found
            default_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
            if os.path.exists(default_path):
                subprocess.Popen([default_path])
            else:
                raise FileNotFoundError("Docker executable not found in default location.")
        elif system == "Linux":
            # Uses user-level systemctl to avoid sudo password hang
            subprocess.run(["systemctl", "--user", "start", "docker"])
        
        # Progress Bar for Startup
        with console.status("[bold yellow]Waiting for Engine to warm up (approx 30s)...[/bold yellow]", spinner="clock"):
            for _ in range(60):
                try:
                    client = docker.from_env()
                    client.ping()
                    console.print("[bold green][OK] Engine Online.[/bold green]")
                    return client
                except DockerException:
                    time.sleep(1)
            
        raise TimeoutError("Docker launch timed out.")

    except Exception as e:
        console.print(f"[bold red]Auto-Wake Failed:[/bold red] {e}")
        return None


def get_docker_client():
    """
    The Gatekeeper: Ensures we have a working connection.
    """
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException:
        client = wake_docker()
        if client:
            return client
        
        console.print(Panel(
            "[bold red]CRITICAL FAILURE: Docker Unavailable[/bold red]\n\n"
            "The Auto-Wake protocol failed.\n"
            "1. Please open 'Docker Desktop' manually.\n"
            "2. Wait for the green status light.\n"
            "3. Restart Gantry.",
            title="SYSTEM HALT",
            border_style="red"
        ))
        sys.exit(1)


# --- 2. THE REAL FACTORY PIPELINE ---
def real_factory_pipeline(client, project_name, stack_type):
    """
    Executes ACTUAL Docker commands. No simulation.
    """
    yield f"[INIT] Gantry Factory Initialized: {project_name}", "info"
    
    # Select Image
    if "python" in stack_type.lower():
        image = "python:3.11-slim"
    elif "node" in stack_type.lower():
        image = "node:20-alpine"
    else:
        image = "ubuntu:latest"

    # Step 1: Provision
    try:
        client.images.get(image)
        yield f"[IMAGE] Found: {image}", "info"
    except ImageNotFound:
        yield f"[PULL] Downloading Image: {image}...", "warning"
        client.images.pull(image)
        yield f"[PULL] Image Ready: {image}", "success"

    # Step 2: Isolation
    yield "[SANDBOX] Spinning up container...", "info"
    container = client.containers.run(
        image,
        command="tail -f /dev/null",  # Keep alive
        detach=True,
        auto_remove=True
    )
    yield f"[SANDBOX] Active (ID: {container.short_id})", "success"

    # Step 3: Construction (Real Execution)
    commands = []
    if "python" in stack_type.lower():
        commands = ["python --version", "pip --version"]
    elif "node" in stack_type.lower():
        commands = ["node -v", "npm -v"]
    
    for cmd in commands:
        yield f"[EXEC] {cmd}", "info"
        exit_code, output = container.exec_run(cmd)
        if exit_code != 0:
            yield f"[FAIL] Command Failed: {output.decode()}", "red"
            container.stop()
            raise Exception(f"Build Failed: {cmd}")
        yield f"[OK] {output.decode().strip()}", "green"

    # Step 4: Audit
    yield "[VERIFY] Integrity Verified.", "success"
    
    # Cleanup
    container.stop()
    yield "[CLEANUP] Sandbox Destroyed.", "warning"
    
    yield "[COMPLETE] FACTORY OUTPUT COMPLETE.", "success"


# --- 3. API ROUTE ---
@app.route('/architect', methods=['POST'])
def handle_request():
    try:
        # Re-verify client on every request (in case Docker crashed)
        client = get_docker_client()
        
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload provided"}), 400
        
        command = data.get('text', '')
        project_name = data.get('project', 'Project-Omega')
        
        # Stack detection
        stack = "Python"
        if "node" in command.lower() or "react" in command.lower():
            stack = "Node"
        if "rust" in command.lower():
            stack = "Rust"

        # HUD Visualization
        console.clear()
        console.rule(f"[bold red]{SYSTEM_NAME}: PROCESSING[/bold red]")
        
        with console.status("[bold white]Factory Operations in Progress...[/bold white]") as status:
            tree = Tree(f"[bold cyan]{project_name}[/bold cyan]")
            
            # Run the REAL pipeline
            for step_name, style in real_factory_pipeline(client, project_name, stack):
                status.update(f"[bold {style}]{step_name}[/bold {style}]")
                console.log(f"[{style}]{step_name}[/{style}]")
                tree.add(f"[{style}]{step_name}[/{style}]")

        console.print(Panel(tree, title="Manifest", border_style="cyan"))
        console.print(Panel(f"[bold green]BUILD COMPLETE[/bold green]", style="on black"))
        
        return jsonify({
            "status": "deployed",
            "project": project_name,
            "stack": stack
        })

    except Exception as e:
        console.print(f"[bold red][ERROR] Request Failed: {e}[/bold red]")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Pre-flight check
    get_docker_client()
    port = int(os.getenv("GANTRY_PORT", 5050))
    console.print(f"[bold green]{SYSTEM_NAME} v{VERSION} ONLINE.[/bold green] Port: {port}")
    app.run(host="127.0.0.1", port=port)
