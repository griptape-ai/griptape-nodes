FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# Install git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
COPY README.md README.md
COPY src src
COPY libraries libraries
# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python:3.12-slim
# Install git in the final image
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Create app directory structure and set permissions for volume mount points
RUN mkdir -p /app/models && \
    chown -R appuser:appuser /app

# Copy the environment with proper ownership
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

LABEL org.opencontainers.image.source="https://github.com/griptape-ai/griptape-nodes"
LABEL org.opencontainers.image.description="Griptape Nodes."
LABEL org.opencontainers.image.licenses="Apache-2.0"

COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user and set working directory
USER appuser
WORKDIR /home/appuser

# Ensure XDG directories and Python user base point to the user's home
ENV HOME=/home/appuser
ENV XDG_CONFIG_HOME=/home/appuser/.config
ENV XDG_DATA_HOME=/home/appuser/.local/share
ENV XDG_CACHE_HOME=/home/appuser/.cache
ENV PYTHONUSERBASE=/home/appuser/.local

EXPOSE 8124
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/app/.venv/bin/griptape-nodes", "--no-update"]
