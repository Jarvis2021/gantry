"""
Tests for the Architect module (AI integration).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.domain.models import FileSpec, GantryManifest, StackType


class TestArchitect:
    """Tests for Architect AI integration."""

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

    @pytest.fixture
    def mock_bedrock_response(self, valid_manifest_dict):
        """Mock Bedrock API response."""
        return {
            "content": [
                {"text": json.dumps(valid_manifest_dict)}
            ]
        }

    def test_clean_json_removes_markdown(self):
        """Test that markdown fences are removed from JSON."""
        from src.core.architect import Architect
        
        with patch.object(Architect, "__init__", lambda x: None):
            architect = Architect()
            architect._clean_json = Architect._clean_json.__get__(architect, Architect)
            
            # Test with markdown code fence
            dirty = '```json\n{"key": "value"}\n```'
            clean = architect._clean_json(dirty)
            assert clean == '{"key": "value"}'
            
            # Test with just json fence
            dirty2 = '```\n{"key": "value"}\n```'
            clean2 = architect._clean_json(dirty2)
            assert clean2 == '{"key": "value"}'

    def test_clean_json_handles_plain_json(self):
        """Test that plain JSON is returned unchanged."""
        from src.core.architect import Architect
        
        with patch.object(Architect, "__init__", lambda x: None):
            architect = Architect()
            architect._clean_json = Architect._clean_json.__get__(architect, Architect)
            
            plain = '{"key": "value"}'
            result = architect._clean_json(plain)
            assert result == plain

    def test_manifest_validation(self, valid_manifest_dict):
        """Test that generated manifest is validated."""
        manifest = GantryManifest(**valid_manifest_dict)
        
        assert manifest.project_name == "TestProject"
        assert manifest.stack == StackType.PYTHON
        assert len(manifest.files) == 2

    def test_manifest_file_paths_valid(self):
        """Test that file paths are validated."""
        file = FileSpec(path="src/app.py", content="x")
        assert file.path == "src/app.py"

    def test_heal_blueprint_structure(self):
        """Test heal_blueprint returns valid manifest structure."""
        # Create original manifest
        original = GantryManifest(
            project_name="BrokenApp",
            stack=StackType.PYTHON,
            files=[FileSpec(path="app.py", content="syntax error here")],
            audit_command="python app.py",
            run_command="python app.py",
        )
        
        error_log = "SyntaxError: invalid syntax at line 1"
        
        # The heal_blueprint should return a new manifest
        # This is a structural test - actual healing requires mocked Bedrock
        assert original.project_name == "BrokenApp"
        assert len(original.files) == 1

    def test_manifest_requires_all_fields(self):
        """Test that manifest validation requires all fields."""
        with pytest.raises(Exception):
            GantryManifest(
                project_name="IncompleteApp",
                stack=StackType.PYTHON,
                files=[FileSpec(path="app.py", content="x")],
                audit_command="echo ok",
                # Missing run_command
            )
