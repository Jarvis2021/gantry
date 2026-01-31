# -----------------------------------------------------------------------------
# GANTRY BUILDER IMAGE
# -----------------------------------------------------------------------------
# A universal build environment for Project Pods.
# Includes: Python 3.11, Node.js 20, Git, Vercel CLI
#
# Why custom image:
# - Standard python:slim or node:slim lack the tools we need
# - Pre-installing Vercel CLI makes deployments instant
# - Consistent environment across all builds
#
# Build: docker build -f builder.Dockerfile -t gantry/builder:latest .
# -----------------------------------------------------------------------------

FROM node:20-slim

LABEL maintainer="Gantry Fleet Protocol"
LABEL description="Universal builder image for Gantry Project Pods"

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11, pip, git, and essential build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create symlinks for python commands
RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# Install Vercel CLI globally
RUN npm install -g vercel@latest

# Verify installations
RUN echo "=== Gantry Builder Environment ===" && \
    echo "Node.js: $(node --version)" && \
    echo "npm: $(npm --version)" && \
    echo "Python: $(python --version)" && \
    echo "pip: $(pip --version)" && \
    echo "Git: $(git --version)" && \
    echo "Vercel: $(vercel --version)" && \
    echo "=================================="

# Set working directory for builds
WORKDIR /workspace

# Default command (keeps container alive for exec commands)
CMD ["tail", "-f", "/dev/null"]
