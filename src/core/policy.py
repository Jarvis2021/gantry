# -----------------------------------------------------------------------------
# THE GATEKEEPER - POLICY ENGINE
# -----------------------------------------------------------------------------
# Responsibility: The Security Bouncer. Validates manifests against policy
# before any Docker operations occur. If a manifest violates policy,
# it is REJECTED with "Access Denied".
#
# "No manifest passes without my approval." - The Gatekeeper
# -----------------------------------------------------------------------------

import re
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel
from rich.console import Console

from src.domain.models import GantryManifest

console = Console()

# Policy file location
POLICY_PATH = Path(__file__).parent.parent.parent / "policy.yaml"


class PolicyConfig(BaseModel):
    """
    Pydantic model for the policy configuration.
    
    Loaded from policy.yaml at startup.
    """
    allowed_stacks: List[str]
    forbidden_patterns: List[str]
    max_files: int = 10


class SecurityViolation(Exception):
    """
    Raised when a manifest violates security policy.
    
    "Access Denied" - Contains details about which rule was violated.
    """
    def __init__(self, message: str, rule: str, details: str = "") -> None:
        super().__init__(message)
        self.rule = rule
        self.details = details


class PolicyGate:
    """
    The Security Bouncer that validates manifests against policy.
    
    Why this exists: Zero-trust principle. Even AI-generated code must be
    validated before execution. The Gatekeeper trusts no one.
    """

    def __init__(self, policy_path: Path = POLICY_PATH) -> None:
        """
        Initialize the Policy Gate.
        
        Args:
            policy_path: Path to the policy YAML file.
        """
        self._policy_path = policy_path
        self._config: PolicyConfig = self._load_policy()
        console.print(f"[green][GATEKEEPER] Policy loaded: {len(self._config.forbidden_patterns)} forbidden patterns[/green]")

    def _load_policy(self) -> PolicyConfig:
        """
        Load policy from YAML file.
        
        Returns:
            PolicyConfig with validated settings.
        """
        if not self._policy_path.exists():
            console.print(f"[yellow][GATEKEEPER] Policy file not found, using defaults[/yellow]")
            return PolicyConfig(
                allowed_stacks=["python", "node", "rust"],
                forbidden_patterns=["rm -rf", "mkfs", r":\(\)\{ :\|:& \};:"],
                max_files=10
            )
        
        with open(self._policy_path) as f:
            data = yaml.safe_load(f)
        
        return PolicyConfig(**data)

    def validate(self, manifest: GantryManifest) -> bool:
        """
        Validate a manifest against all policy rules.
        
        Args:
            manifest: The GantryManifest to validate.
            
        Returns:
            True if validation passes.
            
        Raises:
            SecurityViolation: "Access Denied" if any policy rule is violated.
        """
        console.print(f"[cyan][GATEKEEPER] Validating: {manifest.project_name}[/cyan]")
        
        # Rule 1: Check allowed stacks
        self._check_stack(manifest)
        
        # Rule 2: Check file count
        self._check_file_count(manifest)
        
        # Rule 3: Scan for forbidden patterns
        self._check_forbidden_patterns(manifest)
        
        console.print(f"[green][GATEKEEPER] Access Granted: {manifest.project_name}[/green]")
        return True

    def _check_stack(self, manifest: GantryManifest) -> None:
        """Check if the stack is allowed."""
        stack_value = manifest.stack.value if hasattr(manifest.stack, 'value') else str(manifest.stack)
        
        if stack_value.lower() not in [s.lower() for s in self._config.allowed_stacks]:
            console.print(f"[red][GATEKEEPER] Access Denied: Stack '{stack_value}' not allowed[/red]")
            raise SecurityViolation(
                f"Access Denied: Stack '{stack_value}' is not allowed",
                rule="allowed_stacks",
                details=f"Allowed: {self._config.allowed_stacks}"
            )

    def _check_file_count(self, manifest: GantryManifest) -> None:
        """Check if file count is within limits."""
        if len(manifest.files) > self._config.max_files:
            console.print(f"[red][GATEKEEPER] Access Denied: Too many files[/red]")
            raise SecurityViolation(
                f"Access Denied: Too many files ({len(manifest.files)} > {self._config.max_files})",
                rule="max_files",
                details=f"Maximum allowed: {self._config.max_files}"
            )

    def _check_forbidden_patterns(self, manifest: GantryManifest) -> None:
        """Scan file contents for forbidden patterns."""
        for file_spec in manifest.files:
            for pattern in self._config.forbidden_patterns:
                if re.search(pattern, file_spec.content, re.IGNORECASE):
                    console.print(f"[red][GATEKEEPER] Access Denied: Forbidden pattern in {file_spec.path}[/red]")
                    raise SecurityViolation(
                        f"Access Denied: Forbidden pattern detected in {file_spec.path}",
                        rule="forbidden_patterns",
                        details=f"Pattern: {pattern}"
                    )
