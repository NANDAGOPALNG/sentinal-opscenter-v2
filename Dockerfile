# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev)
RUN uv sync --no-dev --frozen

# Copy the rest of the application
COPY . .

# Expose the port Render expects
ENV PORT=8000
EXPOSE $PORT

# Run with uvicorn (single worker for SQLite)
CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]