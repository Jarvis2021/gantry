# -----------------------------------------------------------------------------
# INFRASTRUCTURE LAYER
# -----------------------------------------------------------------------------
# Contains low-level infrastructure wrappers:
# - DockerProvider: Robust Docker SDK wrapper with auto-wake capability
# -----------------------------------------------------------------------------

from .docker_client import DockerProvider

__all__ = ["DockerProvider"]
