# Copyright 2026 Pramod Kumar Voola
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -----------------------------------------------------------------------------
# DOMAIN MODELS - FABRICATION INSTRUCTIONS
# -----------------------------------------------------------------------------
# These Pydantic models define the "Fabrication Instructions" for Project Pods.
# The Architect (Brain) generates these; the Foundry (Body) executes them blindly.
#
# Why strict typing: Ensures the AI output is valid before any Docker
# operations begin. Invalid manifests are rejected at the gate.
# -----------------------------------------------------------------------------

from enum import Enum

from pydantic import BaseModel, Field


class StackType(str, Enum):
    """
    Supported technology stacks for Project Pods.

    Why an Enum: Constrains the AI to only output valid stack types,
    preventing hallucinated or unsupported configurations.
    Each stack maps to a specific Docker base image.
    """

    PYTHON = "python"
    NODE = "node"
    RUST = "rust"


class FileSpec(BaseModel):
    """
    Fabrication Instruction: A single file to inject into the Pod.

    The Architect specifies what files to create; the Foundry
    materializes them inside the container using tarfile injection.

    Why separate model: Allows the Manifest to declare multiple files
    with clear paths and contents, enabling multi-file project generation.
    """

    path: str = Field(
        ..., description="Relative path inside the Pod (e.g., 'app.py', 'src/main.rs')"
    )
    content: str = Field(..., description="The full content of the file to be written")


class GantryManifest(BaseModel):
    """
    The Master Fabrication Instructions for a Project Pod.

    This is the contract between the Architect (AI Brain) and the Foundry
    (Docker Body). The Architect generates this JSON; the Foundry executes
    it without question.

    Fields:
    - project_name: Human-readable identifier for logging and container naming
    - stack: Determines which base image to use (python:3.11-slim, node:20-alpine, etc.)
    - files: All source files to inject into the Pod
    - audit_command: The Critic's verification command (must pass before deploy)
    - run_command: How to start the application after audit passes

    The "Gantry Guarantee": Code only deploys if audit_command exits with 0.
    """

    project_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        description="Project identifier (alphanumeric, starts with letter)",
    )
    stack: StackType = Field(..., description="Technology stack determining the base Docker image")
    files: list[FileSpec] = Field(
        ..., min_length=1, description="Fabrication instructions: files to inject into the Pod"
    )
    audit_command: str = Field(
        ..., min_length=1, description="The Critic's test command (e.g., 'pytest', 'npm test')"
    )
    run_command: str = Field(
        ...,
        min_length=1,
        description="Deploy command to start the application (e.g., 'python app.py')",
    )

    class Config:
        """Pydantic configuration for strict validation."""

        str_strip_whitespace = True
        use_enum_values = True
