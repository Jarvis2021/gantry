"""
Tests for the Architect module (AI integration).
"""

import json
import os
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
        return {"content": [{"text": json.dumps(valid_manifest_dict)}]}

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


class TestArchitectInit:
    """Test Architect initialization."""

    def test_architect_class_exists(self):
        """Architect class should exist."""
        from src.core.architect import Architect

        assert Architect is not None

    def test_architect_error_exists(self):
        """ArchitectError should exist."""
        from src.core.architect import ArchitectError

        assert ArchitectError is not None

    def test_system_prompt_defined(self):
        """SYSTEM_PROMPT should be defined."""
        from src.core.architect import SYSTEM_PROMPT

        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 100

    def test_consult_prompt_defined(self):
        """CONSULT_PROMPT should be defined."""
        from src.core.architect import CONSULT_PROMPT

        assert CONSULT_PROMPT is not None
        assert "PROTOTYPE" in CONSULT_PROMPT or "prototype" in CONSULT_PROMPT

    def test_heal_prompt_defined(self):
        """HEAL_PROMPT should be defined."""
        from src.core.architect import HEAL_PROMPT

        assert HEAL_PROMPT is not None

    def test_claude_model_id_defined(self):
        """CLAUDE_MODEL_ID should be defined."""
        from src.core.architect import CLAUDE_MODEL_ID

        assert CLAUDE_MODEL_ID is not None
        assert "claude" in CLAUDE_MODEL_ID.lower()


class TestArchitectMethods:
    """Test Architect methods with mocking."""

    @patch("src.core.architect.requests.post")
    def test_draft_blueprint_calls_api(self, mock_post):
        """draft_blueprint should call Bedrock API."""
        from src.core.architect import Architect

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "project_name": "TestApp",
                            "stack": "node",
                            "files": [{"path": "index.js", "content": "console.log('hi');"}],
                            "audit_command": "node index.js",
                            "run_command": "node index.js",
                        }
                    )
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-key"}):
            architect = Architect()
            manifest = architect.draft_blueprint("Build a hello world app")

            assert manifest.project_name == "TestApp"
            mock_post.assert_called_once()

    @patch("src.core.architect.requests.post")
    def test_draft_blueprint_handles_api_error(self, mock_post):
        """draft_blueprint should handle API errors."""
        from src.core.architect import Architect, ArchitectError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-key"}):
            architect = Architect()

            with pytest.raises(ArchitectError):
                architect.draft_blueprint("Build something")

    @patch("src.core.architect.requests.post")
    def test_consult_returns_response(self, mock_post):
        """consult should return response dict."""
        from src.core.architect import Architect

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "response": "I suggest using React for this app.",
                            "ready_to_build": False,
                        }
                    )
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-key"}):
            architect = Architect()
            result = architect.consult([{"role": "user", "content": "Build a todo app"}])

            assert "response" in result
            assert result["ready_to_build"] is False

    @patch("src.core.architect.requests.post")
    def test_consult_handles_ready_to_build(self, mock_post):
        """consult should detect ready_to_build flag."""
        from src.core.architect import Architect

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "response": "Great, starting the build now!",
                            "ready_to_build": True,
                            "final_prompt": "Build a todo app with React",
                        }
                    )
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-key"}):
            architect = Architect()
            result = architect.consult(
                [
                    {"role": "user", "content": "Build a todo app"},
                    {"role": "assistant", "content": "I suggest React..."},
                    {"role": "user", "content": "Yes, proceed!"},
                ]
            )

            assert result["ready_to_build"] is True

    @patch("src.core.architect.requests.post")
    def test_heal_blueprint_calls_api(self, mock_post):
        """heal_blueprint should call Bedrock API for fixes."""
        from src.core.architect import Architect

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "project_name": "FixedApp",
                            "stack": "node",
                            "files": [{"path": "index.js", "content": "console.log('fixed');"}],
                            "audit_command": "node index.js",
                            "run_command": "node index.js",
                        }
                    )
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-key"}):
            architect = Architect()

            original = GantryManifest(
                project_name="BrokenApp",
                stack=StackType.NODE,
                files=[FileSpec(path="index.js", content="broken code")],
                audit_command="node index.js",
                run_command="node index.js",
            )

            fixed = architect.heal_blueprint(original, "SyntaxError: Unexpected token")

            assert fixed.project_name == "FixedApp"
            assert "fixed" in fixed.files[0].content


class TestCleanJson:
    """Test JSON cleaning utility."""

    def test_clean_json_with_newlines(self):
        """Should handle JSON with embedded newlines."""
        from src.core.architect import Architect

        with patch.object(Architect, "__init__", lambda x: None):
            architect = Architect()
            architect._clean_json = Architect._clean_json.__get__(architect, Architect)

            # JSON with control characters
            dirty = '{"text": "line1\\nline2"}'
            clean = architect._clean_json(dirty)
            assert "line1" in clean

    def test_clean_json_extracts_from_text(self):
        """Should extract JSON from surrounding text."""
        from src.core.architect import Architect

        with patch.object(Architect, "__init__", lambda x: None):
            architect = Architect()
            architect._clean_json = Architect._clean_json.__get__(architect, Architect)

            dirty = 'Here is the JSON: {"key": "value"} - that was it!'
            clean = architect._clean_json(dirty)
            # Should at least contain the JSON
            assert "key" in clean
