FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /griptape-nodes

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

# Copy the environment, but not the source code
COPY --from=builder --chown=griptape-nodes:griptape-nodes /griptape-nodes/.venv /griptape-nodes/.venv

LABEL org.opencontainers.image.source="https://github.com/griptape-ai/griptape-nodes"
LABEL org.opencontainers.image.description="Griptape Nodes."
LABEL org.opencontainers.image.licenses="Apache-2.0"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8124

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/griptape-nodes/.venv/bin/griptape-nodes", "--no-update"]
