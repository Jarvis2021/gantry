"""
Tests for security policy enforcement.
"""

import pytest
from src.core.policy import PolicyGate, SecurityViolation
from src.domain.models import FileSpec, GantryManifest, StackType


class TestPolicyGate:
    """Tests for PolicyGate security enforcement."""

    @pytest.fixture
    def policy_gate(self):
        """Create a PolicyGate instance."""
        return PolicyGate()

    @pytest.fixture
    def valid_manifest(self):
        """Create a valid Python manifest."""
        return GantryManifest(
            project_name="SafeApp",
            stack=StackType.PYTHON,
            files=[
                FileSpec(path="app.py", content="from flask import Flask\napp = Flask(__name__)"),
                FileSpec(path="requirements.txt", content="flask"),
            ],
            audit_command="python -m py_compile app.py",
            run_command="python app.py",
        )

    def test_valid_python_manifest_passes(self, policy_gate, valid_manifest):
        """Test that a valid Python manifest passes validation."""
        # Should not raise
        policy_gate.validate(valid_manifest)

    def test_forbidden_pattern_import_fails(self, policy_gate):
        """Test that __import__() usage is caught (dynamic import)."""
        manifest = GantryManifest(
            project_name="DangerApp",
            stack=StackType.PYTHON,
            files=[
                FileSpec(path="evil.py", content="m = __import__('os')"),
            ],
            audit_command="python evil.py",
            run_command="python evil.py",
        )
        with pytest.raises(SecurityViolation) as exc_info:
            policy_gate.validate(manifest)
        assert "evil.py" in str(exc_info.value)

    def test_forbidden_pattern_os_system_fails(self, policy_gate):
        """Test that os.system() usage is caught."""
        manifest = GantryManifest(
            project_name="DangerApp",
            stack=StackType.PYTHON,
            files=[
                FileSpec(path="evil.py", content="os.system('rm -rf /tmp/x')"),
            ],
            audit_command="python evil.py",
            run_command="python evil.py",
        )
        with pytest.raises(SecurityViolation) as exc_info:
            policy_gate.validate(manifest)
        assert "evil.py" in str(exc_info.value)

    def test_forbidden_pattern_subprocess_shell_fails(self, policy_gate):
        """Test that shell=True usage is caught."""
        manifest = GantryManifest(
            project_name="DangerApp",
            stack=StackType.PYTHON,
            files=[
                FileSpec(path="cmd.py", content="subprocess.run('ls', shell=True)"),
            ],
            audit_command="python cmd.py",
            run_command="python cmd.py",
        )
        with pytest.raises(SecurityViolation) as exc_info:
            policy_gate.validate(manifest)
        assert "cmd.py" in str(exc_info.value)

    def test_node_stack_allowed(self, policy_gate):
        """Test that Node.js stack is allowed."""
        manifest = GantryManifest(
            project_name="NodeApp",
            stack=StackType.NODE,
            files=[
                FileSpec(path="index.js", content="console.log('hello')"),
            ],
            audit_command="node -c index.js",
            run_command="node index.js",
        )
        # Should not raise
        policy_gate.validate(manifest)

    def test_rust_stack_allowed(self, policy_gate):
        """Test that Rust stack is allowed."""
        manifest = GantryManifest(
            project_name="RustApp",
            stack=StackType.RUST,
            files=[
                FileSpec(path="main.rs", content='fn main() { println!("hi"); }'),
            ],
            audit_command="rustc --emit=metadata main.rs",
            run_command="./main",
        )
        # Should not raise
        policy_gate.validate(manifest)

    def test_safe_commands_allowed(self, policy_gate):
        """Test that safe audit commands are allowed."""
        manifest = GantryManifest(
            project_name="SafeApp",
            stack=StackType.PYTHON,
            files=[
                FileSpec(path="app.py", content="print('hi')"),
            ],
            audit_command="python -m py_compile app.py",
            run_command="python app.py",
        )
        # Should not raise - safe commands are allowed
        policy_gate.validate(manifest)

    def test_multiple_files_with_one_dangerous(self, policy_gate):
        """Test that dangerous patterns are caught in multi-file manifests."""
        manifest = GantryManifest(
            project_name="MixedApp",
            stack=StackType.PYTHON,
            files=[
                FileSpec(path="safe.py", content="print('safe')"),
                FileSpec(path="danger.py", content="os.system('rm -rf /')"),
                FileSpec(path="also_safe.py", content="x = 1 + 1"),
            ],
            audit_command="python safe.py",
            run_command="python safe.py",
        )
        with pytest.raises(SecurityViolation) as exc_info:
            policy_gate.validate(manifest)
        assert "danger.py" in str(exc_info.value)
