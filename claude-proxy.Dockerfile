# claude-proxy.Dockerfile
FROM python:3.11-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install git if needed, though usually not required if you're COPYing local code
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Copy only dependency files first to leverage Docker layer caching
COPY proxy_project/pyproject.toml .
COPY proxy_project/uv.lock .

# 2. Sync dependencies (without the project itself yet)
RUN uv sync --frozen 

# 3. Copy the actual project code
# This assumes your Dockerfile is in the root and your code is in proxy_project/
COPY proxy_project/ .

EXPOSE 8083

# 4. Update the CMD to point to main.py inside the proxy_project directory
# We set the PYTHONPATH to the current directory so 'from app.x import y' works
ENV PYTHONPATH=/app
CMD ["uv", "run", "python", "main.py"]