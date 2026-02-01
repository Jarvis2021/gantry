# -----------------------------------------------------------------------------
# GANTRY SKILLS - PLUGGABLE ARCHITECTURE
# -----------------------------------------------------------------------------
# Skills are modular capabilities that the Architect can use.
# Each skill is a folder with:
#   - SKILL.md - Description and usage
#   - handler.py - The skill implementation
#   - __init__.py - Exports
# -----------------------------------------------------------------------------

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from rich.console import Console

console = Console()

# Skills directory
SKILLS_DIR = Path(__file__).parent


class SkillResult(BaseModel):
    """Result from executing a skill."""

    success: bool
    data: dict | None = None
    error: str | None = None


class Skill(Protocol):
    """Protocol for skills - defines the interface all skills must implement."""

    name: str
    description: str

    async def execute(self, context: dict) -> SkillResult:
        """Execute the skill with given context."""
        ...


class SkillRegistry:
    """
    Registry for dynamically loaded skills.

    Skills are loaded from the skills/ folder at startup.
    Each skill folder must have a handler.py with a `skill` object.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill."""
        self._skills[skill.name] = skill
        console.print(f"[green][SKILLS] Registered: {skill.name}[/green]")

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """List all registered skill names."""
        return list(self._skills.keys())

    def load_all(self) -> None:
        """Load all skills from the skills directory."""
        for skill_dir in SKILLS_DIR.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith("_"):
                self._load_skill(skill_dir)

    def _load_skill(self, skill_dir: Path) -> None:
        """Load a single skill from a directory."""
        handler_path = skill_dir / "handler.py"
        if not handler_path.exists():
            return

        try:
            # Dynamic import
            import importlib.util

            spec = importlib.util.spec_from_file_location(f"skills.{skill_dir.name}", handler_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "skill"):
                    self.register(module.skill)
                else:
                    console.print(
                        f"[yellow][SKILLS] No 'skill' object in {skill_dir.name}[/yellow]"
                    )
        except Exception as e:
            console.print(f"[red][SKILLS] Failed to load {skill_dir.name}: {e}[/red]")


# Global registry
registry = SkillRegistry()


def load_skills() -> None:
    """Load all skills at startup."""
    registry.load_all()
    console.print(f"[green][SKILLS] Loaded {len(registry.list_skills())} skills[/green]")
