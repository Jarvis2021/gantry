"""
Tests for Pydantic domain models.
"""

import pytest
from pydantic import ValidationError

from src.domain.models import FileSpec, GantryManifest, StackType


class TestFileSpec:
    """Tests for FileSpec model."""

    def test_valid_file_spec(self):
        """Test creating a valid FileSpec."""
        file = FileSpec(path="main.py", content="print('hello')")
        assert file.path == "main.py"
        assert file.content == "print('hello')"

    def test_nested_path(self):
        """Test nested file paths."""
        file = FileSpec(path="src/utils/helpers.py", content="# helpers")
        assert file.path == "src/utils/helpers.py"

    def test_empty_content_allowed(self):
        """Test that empty content is allowed (for empty files)."""
        file = FileSpec(path="empty.txt", content="")
        assert file.content == ""


class TestStackType:
    """Tests for StackType enum."""

    def test_valid_stack_types(self):
        """Test all valid stack types."""
        assert StackType.PYTHON.value == "python"
        assert StackType.NODE.value == "node"
        assert StackType.RUST.value == "rust"

    def test_stack_type_from_string(self):
        """Test creating StackType from string."""
        assert StackType("python") == StackType.PYTHON
        assert StackType("node") == StackType.NODE
        assert StackType("rust") == StackType.RUST

    def test_invalid_stack_type(self):
        """Test that invalid stack type raises error."""
        with pytest.raises(ValueError):
            StackType("invalid")


class TestGantryManifest:
    """Tests for GantryManifest model."""

    @pytest.fixture
    def valid_manifest_dict(self):
        """Valid manifest dictionary for testing."""
        return {
            "project_name": "TestProject",
            "stack": "python",
            "files": [
                {"path": "app.py", "content": "from flask import Flask\napp = Flask(__name__)"},
                {"path": "requirements.txt", "content": "flask==3.0.0"},
            ],
            "audit_command": "python -m py_compile app.py",
            "run_command": "python app.py",
        }

    def test_valid_manifest(self, valid_manifest_dict):
        """Test creating a valid manifest."""
        manifest = GantryManifest(**valid_manifest_dict)
        assert manifest.project_name == "TestProject"
        assert manifest.stack == StackType.PYTHON
        assert len(manifest.files) == 2
        assert manifest.audit_command == "python -m py_compile app.py"
        assert manifest.run_command == "python app.py"

    def test_manifest_with_node_stack(self):
        """Test manifest with Node.js stack."""
        manifest = GantryManifest(
            project_name="NodeApp",
            stack=StackType.NODE,
            files=[FileSpec(path="index.js", content="console.log('hi')")],
            audit_command="node -c index.js",
            run_command="node index.js",
        )
        assert manifest.stack == StackType.NODE

    def test_manifest_requires_files(self):
        """Test that manifest requires at least one file."""
        with pytest.raises(ValidationError):
            GantryManifest(
                project_name="Empty",
                stack=StackType.PYTHON,
                files=[],
                audit_command="echo ok",
                run_command="echo ok",
            )

    def test_manifest_requires_project_name(self):
        """Test that manifest requires a valid project name."""
        with pytest.raises(ValidationError):
            GantryManifest(
                project_name="",
                stack=StackType.PYTHON,
                files=[FileSpec(path="a.py", content="x")],
                audit_command="echo ok",
                run_command="echo ok",
            )

    def test_manifest_project_name_pattern(self):
        """Test project name must start with letter."""
        with pytest.raises(ValidationError):
            GantryManifest(
                project_name="123invalid",
                stack=StackType.PYTHON,
                files=[FileSpec(path="a.py", content="x")],
                audit_command="echo ok",
                run_command="echo ok",
            )

    def test_manifest_json_serialization(self, valid_manifest_dict):
        """Test manifest can be serialized to JSON."""
        manifest = GantryManifest(**valid_manifest_dict)
        json_str = manifest.model_dump_json()
        assert "TestProject" in json_str
        assert "python" in json_str

    def test_manifest_from_json(self, valid_manifest_dict):
        """Test manifest can be created from JSON."""
        manifest = GantryManifest(**valid_manifest_dict)
        json_str = manifest.model_dump_json()
        
        # Recreate from JSON
        recreated = GantryManifest.model_validate_json(json_str)
        assert recreated.project_name == manifest.project_name
        assert len(recreated.files) == len(manifest.files)

    def test_manifest_requires_run_command(self):
        """Test that run_command is required."""
        with pytest.raises(ValidationError):
            GantryManifest(
                project_name="TestApp",
                stack=StackType.PYTHON,
                files=[FileSpec(path="a.py", content="x")],
                audit_command="echo ok",
                # Missing run_command
            )
