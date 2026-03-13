# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a proxy server that translates between the Anthropic API and LiteLLM, enabling Claude Code to work with local LLM backends (vLLM or llama.cpp/GGUF). The project is part of a larger deployment system for Qwen models on NVIDIA DGX hardware.

## Architecture

The proxy uses a modular architecture in `app/`:

- **`config.py`** - Environment-based configuration (API keys, model names, context window settings)
- **`models.py`** - Pydantic models for request/response validation, tool schemas, and thinking config
- **`routes.py`** - FastAPI endpoints (`/v1/messages`, `/v1/messages/count_tokens`, `/v1/models`)
- **`converter.py`** - Bidirectional translation between Anthropic and OpenAI/LiteLLM formats
- **`utils.py`** - Logging helpers, schema cleaning for Gemini, beautiful console output

## Key Design Patterns

**Model Mapping Logic** (`routes.py:68-103`): The proxy automatically maps Claude model names to backend models:
- Haiku/Mini/Flash → SMALL_MODEL (e.g., gpt-4.1-mini)
- Sonnet/Opus/Pro/GPT-4 → BIG_MODEL (e.g., gpt-4.1)
- Explicit model names are preserved if they match `OPENAI_MODELS` or `GEMINI_MODELS`

**Tool Call Schema Coercion** (`converter.py:35-77`): Normalizes tool arguments from various LLM outputs to satisfy Claude Code's strict Zod schemas (sub-agents, TodoWrite, etc.)

**Streaming Format** (`converter.py:214-312`): Generates Anthropic-compatible streaming events (message_start, content_block_start/delta/stop, message_delta/stop)

## Development Commands

```bash
# Install dependencies (requires uv)
uv sync

# Run the proxy server
uv run python main.py

# Run tests (if any)
uv run pytest

# Lint
uv run ruff check .
```

## Deployment

The proxy runs in Docker. Build and start with:

```bash
# Using the up.sh wrapper (recommended)
./up.sh proxy-up

# Or directly with docker-compose
docker compose --profile proxy up -d --build
```

Environment variables (in `.env` or docker-compose):
- `OPENAI_BASE_URL` - Backend endpoint (e.g., `http://qwen3-vllm:8000/v1`)
- `OPENAI_API_KEY` - Dummy key for local backends
- `PREFERRED_PROVIDER` - Either "openai" or "google"
- `BIG_MODEL` / `SMALL_MODEL` - Backend model identifiers
- `CLAUDE_MODEL_ALIAS` - Model name advertised to Claude Code

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/messages` | Create chat completion (Anthropic-compatible) |
| POST | `/v1/messages/count_tokens` | Count tokens in messages |
| GET | `/v1/models` | List available models |
| GET | `/v1/models/{model_id}` | Get model details |
| GET | `/` | Health check |

## Integration with Claude Code

Point Claude Code's custom API base to `http://localhost:8083` (or the Docker container IP). The proxy will:
1. Accept Anthropic API requests
2. Convert to LiteLLM/OpenAI format
3. Route to local vLLM or GGUF backend
4. Convert responses back to Anthropic format
