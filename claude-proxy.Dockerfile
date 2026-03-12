# claude-proxy.Dockerfile
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone https://github.com/1rgs/claude-code-proxy.git .
RUN uv sync --frozen

EXPOSE 8083

# Must use 0.0.0.0 so the port maps correctly to your host machine
CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8083"]