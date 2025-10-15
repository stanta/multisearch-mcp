# Multi-stage build for optimal image size
FROM python:3.13-slim as builder

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Production stage
FROM python:3.13-slim

# Add labels for better container management
LABEL org.opencontainers.image.title="Multisearch MCP Server" \
      org.opencontainers.image.description="Unified multi-category DDGS MCP server" \
      org.opencontainers.image.vendor="Docker" \
      org.opencontainers.image.source="https://github.com/docker/multisearch-mcp"

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r mcpuser && useradd -r -g mcpuser mcpuser

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder stage
COPY --from=builder --chown=mcpuser:mcpuser /app/.venv /app/.venv

# Copy application code
COPY --chown=mcpuser:mcpuser . .

# Switch to non-root user
USER mcpuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Ephemeral by design: container exits when stdin closes; Docker will auto-remove with `--rm`
# Ensure fast, graceful shutdown on `docker stop`
STOPSIGNAL SIGTERM

# Health check for MCP server
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD ["python","-c","import importlib,sys; importlib.import_module('servers.ddgs_multisearch.server'); print('ok')"]

# Default command - use stdio launcher so MCP clients can attach over stdin/stdout
CMD ["python", "serve.py"]