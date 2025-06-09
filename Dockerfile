# Single Dockerfile for both CPU and GPU type builds.
# Use --build-arg BUILD_TYPE=cpu (default) or BUILD_TYPE=gpu to switch modes.

#────────────────────────────
# 1) ARGs and base‐image definitions
#────────────────────────────
ARG BUILD_TYPE=cpu
ARG BASE_IMAGE_CPU=python:3.12-slim
ARG BASE_IMAGE_GPU=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

#────────────────────────────
# 2) CPU builder stage
#────────────────────────────
FROM ${BASE_IMAGE_CPU} AS builder_cpu

# Bring in uv/uvx binaries from the official Astral SH image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install git (needed for uv to fetch dependencies) and build tools for native packages
RUN apt-get update \
 && apt-get install -y git build-essential pkg-config cmake libprotobuf-dev protobuf-compiler \
 && rm -rf /var/lib/apt/lists/* \
 && pkg-config --version \
 && cmake --version

WORKDIR /app

# Set virtual environment location outside of /app to avoid mount conflicts
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# 2.1) Install dependencies (without yet installing the project itself)
#     - Use BuildKit cache mounts for pip/uv caches
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python3.12
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# 2.2) Copy everything needed for the actual project sync
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
COPY README.md README.md
COPY src src
COPY libraries libraries

# 2.3) Install the project (puts it into a venv at /app/.venv)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


#────────────────────────────
# 3) GPU builder stage
#────────────────────────────
FROM ${BASE_IMAGE_GPU} AS builder_gpu

# Force noninteractive front‐end and set a dummy TZ so tzdata won’t prompt
# Bring in uv/uvx binaries from the official Astral SH image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# 3.1) Install prerequisites and add Deadsnakes for Python 3.12
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      software-properties-common \
      wget \
      tzdata \
 && ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime \
 && dpkg-reconfigure -f noninteractive tzdata \
 && add-apt-repository ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      ffmpeg libgl1 \
      libjpeg-dev zlib1g-dev libpng-dev libwebp-dev \
      build-essential \
      pkg-config \
      cmake \
      libprotobuf-dev \
      protobuf-compiler \
      python3.12 \
      python3.12-dev \
      python3.12-venv \
 && rm -rf /var/lib/apt/lists/* \
 && pkg-config --version \
 && cmake --version

WORKDIR /app

# Set virtual environment location outside of /app to avoid mount conflicts
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# 3.2) Install dependencies (without yet installing the project itself)
#     - Use BuildKit cache mounts for pip/uv caches
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/bin/python3.12
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# 3.3) Copy everything needed for the actual project sync
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
COPY README.md README.md
COPY src src
COPY libraries libraries

# 3.4) Install the project (puts it into a venv at /opt/venv)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


#────────────────────────────
# 4) "builder" alias: pick CPU or GPU builder based on BUILD_TYPE
#────────────────────────────
FROM builder_${BUILD_TYPE} AS builder


#────────────────────────────
# 5) CPU runtime stage
#────────────────────────────
FROM ${BASE_IMAGE_CPU} AS runtime_cpu

# Install git (needed by entrypoint if it ever pulls from Git, etc.) and build tools
RUN apt-get update \
 && apt-get install -y git libgl1-mesa-glx libglib2.0-0 build-essential pkg-config cmake libprotobuf-dev protobuf-compiler \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app


#────────────────────────────
# 6) GPU runtime stage
#────────────────────────────
FROM ${BASE_IMAGE_GPU} AS runtime_gpu

# Install libraries needed at runtime and build tools
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      software-properties-common \
      tzdata \
 && ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime \
 && dpkg-reconfigure -f noninteractive tzdata \
 && add-apt-repository ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      git ffmpeg libgl1 \
      libjpeg-dev zlib1g-dev libpng-dev libwebp-dev \
      build-essential pkg-config cmake libprotobuf-dev protobuf-compiler \
      python3.12 python3.12-dev python3.12-venv \
 && rm -rf /var/lib/apt/lists/* \
 && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
 && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

WORKDIR /app


#────────────────────────────
# 7) Final stage: pick runtime_${BUILD_TYPE}, then add user / copy venv / entrypoint
#────────────────────────────
ARG BUILD_TYPE
FROM runtime_${BUILD_TYPE} AS final

# 7.1) Create a non-root user and prepare /app/models
RUN groupadd --gid 1000 appuser \
 && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser 

# Create app directory structure and set permissions for volume mount points
RUN mkdir -p /app /opt/venv && \
    chown -R appuser:appuser /app /opt/venv

# 7.2) Copy the venv from the chosen builder into /opt/venv, preserving ownership
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

LABEL org.opencontainers.image.source="https://github.com/griptape-ai/griptape-nodes"
LABEL org.opencontainers.image.description="Griptape Nodes."
LABEL org.opencontainers.image.licenses="Apache-2.0"

# 7.3) Copy entrypoint and make sure it’s executable
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 7.4) Switch to non-root user and set working directory
USER appuser
WORKDIR /app

# Ensure XDG directories and Python user base point to the user's home
ENV HOME=/app

EXPOSE 8124

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/opt/venv/bin/griptape-nodes", "--no-update"]
