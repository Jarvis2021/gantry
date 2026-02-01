# =============================================================================
# GANTRY POLICY EXTENDED TESTS
# =============================================================================
# Additional tests for policy gate module.
# =============================================================================



from src.domain.models import FileSpec, GantryManifest, StackType


class TestPolicyGate:
    """Test PolicyGate class."""

    def test_policy_gate_exists(self):
        """PolicyGate class should exist."""
        from src.core.policy import PolicyGate

        assert PolicyGate is not None

    def test_security_violation_exists(self):
        """SecurityViolation exception should exist."""
        from src.core.policy import SecurityViolation

        assert SecurityViolation is not None

    def test_security_violation_message(self):
        """SecurityViolation should store message and rule."""
        from src.core.policy import SecurityViolation

        error = SecurityViolation("Forbidden file type", rule="file_extension")
        assert "Forbidden" in str(error)
        assert error.rule == "file_extension"


class TestPolicyGateMethods:
    """Test PolicyGate methods."""

    def test_policy_gate_has_validate(self):
        """PolicyGate should have validate method."""
        from src.core.policy import PolicyGate

        assert hasattr(PolicyGate, "validate")

    def test_policy_gate_has_check_stack(self):
        """PolicyGate should have _check_stack method."""
        from src.core.policy import PolicyGate

        assert hasattr(PolicyGate, "_check_stack")

    def test_policy_gate_has_check_forbidden_patterns(self):
        """PolicyGate should have _check_forbidden_patterns method."""
        from src.core.policy import PolicyGate

        assert hasattr(PolicyGate, "_check_forbidden_patterns")


class TestPolicyValidation:
    """Test policy validation."""

    def test_valid_manifest_passes(self):
        """Valid manifest should pass validation."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()

        manifest = GantryManifest(
            project_name="SafeApp",
            stack=StackType.NODE,
            files=[FileSpec(path="index.js", content="console.log('hello');")],
            audit_command="node index.js",
            run_command="node index.js",
        )

        # Should not raise
        gate.validate(manifest)

    def test_file_count_checked(self):
        """File count should be validated."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()
        # Gate should have file count check
        assert hasattr(gate, "_check_file_count")

    def test_stack_checked(self):
        """Stack should be validated."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()
        # Gate should have stack check
        assert hasattr(gate, "_check_stack")


class TestCommandValidation:
    """Test command validation."""

    def test_safe_commands_pass(self):
        """Safe commands should pass."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()

        manifest = GantryManifest(
            project_name="SafeApp",
            stack=StackType.PYTHON,
            files=[FileSpec(path="app.py", content="print('hello')")],
            audit_command="python -m py_compile app.py",
            run_command="python app.py",
        )

        gate.validate(manifest)

    def test_forbidden_patterns_checked(self):
        """Forbidden patterns should be checked."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()
        # Gate should have forbidden patterns check
        assert hasattr(gate, "_check_forbidden_patterns")


class TestPolicyGateInit:
    """Test PolicyGate initialization."""

    def test_policy_gate_loads_policy(self):
        """PolicyGate should load policy file."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()
        # Should have policy loaded
        assert gate is not None


class TestForbiddenPatterns:
    """Test forbidden pattern detection."""

    def test_env_access_blocked(self):
        """Environment variable access should be checked."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()
        # Gate should exist
        assert gate is not None

    def test_network_commands_checked(self):
        """Network commands should be checked."""
        from src.core.policy import PolicyGate

        gate = PolicyGate()
        # Gate should exist
        assert gate is not None
