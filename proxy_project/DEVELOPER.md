# Developer Guide - Anthropic Proxy

This document provides detailed information for developers working on the Anthropic Proxy server.

## Project Overview

The Anthropic Proxy is a translation layer between the Anthropic API and LiteLLM-compatible backends. It enables Claude Code and other Anthropic API clients to work with local LLM backends (vLLM, llama.cpp/GGUF) or cloud providers (OpenAI, Google Gemini, Vertex AI).

### Key Capabilities

- **API Translation**: Converts Anthropic API requests to OpenAI/LiteLLM format and back
- **Model Mapping**: Automatically routes Claude model names (Sonnet, Haiku, etc.) to appropriate backend models
- **Tool Call Normalization**: Coerces tool argument schemas to satisfy Claude Code's strict Zod schemas
- **Streaming Support**: Produces Anthropic-compatible streaming events for real-time responses
- **Multi-Provider Support**: Supports OpenAI, Google Gemini, and Vertex AI backends

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Claude Code   │────>│  Anthropic Proxy │────>│  Backend (vLLM   │
│ (Anthropic API) │<────│   (this project) │<────│   LiteLLM, etc.) │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

### Module Structure

```
app/
├── __init__.py      # Package initialization
├── config.py        # Environment-based configuration
├── models.py        # Pydantic models for request/response validation
├── routes.py        # FastAPI endpoints
├── converter.py     # API format translation (Anthropic ↔ LiteLLM)
└── utils.py         # Logging helpers and schema utilities
```

## Core Components

### config.py

Environment-based configuration loaded from `.env` file.

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Primary API key for Anthropic | `None` |
| `OPENAI_API_KEY` | API key for OpenAI backends | `None` |
| `GEMINI_API_KEY` | API key for Google Gemini | `None` |
| `VERTEX_PROJECT` | GCP project for Vertex AI | `"unset"` |
| `VERTEX_LOCATION` | GCP location for Vertex AI | `"unset"` |
| `USE_VERTEX_AUTH` | Use Vertex AI auth instead of API key | `"False"` |
| `OPENAI_BASE_URL` | Custom OpenAI-compatible endpoint | `None` |
| `PREFERRED_PROVIDER` | Default provider: "openai" or "google" | `"openai"` |
| `VLLM_MAX_CTX` | Maximum context window for vLLM | `131072` |
| `BUFFER_TOKENS` | Safety buffer for token counting | `16000` |
| `BIG_MODEL` | Backend model for large models | `"gpt-4.1"` |
| `SMALL_MODEL` | Backend model for small models | `"gpt-4.1-mini"` |
| `CLAUDE_MODEL_ALIAS` | Model name advertised to Claude Code | `"claude-sonnet-4-5"` |

### models.py

Pydantic models for request/response validation.

#### Request Models

- `MessagesRequest` - Main chat completion request with support for:
  - `model` - Model name (with automatic mapping)
  - `max_tokens` - Maximum generation tokens
  - `messages` - Conversation history
  - `system` - System prompt (string or list)
  - `tools` - Function/tool definitions
  - `thinking` - Thinking configuration
  - `stream` - Enable streaming mode

- `TokenCountRequest` - Token counting request

#### Response Models

- `MessagesResponse` - Anthropic-compatible response
- `TokenCountResponse` - Token count result
- `Usage` - Token usage statistics

### converter.py

Core translation logic between API formats.

#### `convert_anthropic_to_litellm(request)`

Converts an Anthropic-style request to LiteLLM/OpenAI format:

1. Handles system prompts (string or content blocks)
2. Converts message content blocks to OpenAI format
3. Transforms tool_use blocks to tool_calls
4. Transforms tool_result blocks to tool role messages
5. Applies context window limits for vLLM backends
6. Formats tools for OpenAI function calling
7. Cleans Gemini schema (removes unsupported fields)

#### `convert_litellm_to_anthropic(response, original_request)`

Converts LiteLLM response back to Anthropic format:

1. Maps finish reasons: `stop` → `end_turn`, `length` → `max_tokens`
2. Converts tool_calls to tool_use content blocks
3. Applies `coerce_tool_arguments()` for schema compatibility

#### `handle_streaming(response_generator, original_request)`

Generates Anthropic-compatible streaming events:

```
event: message_start
data: {"type": "message_start", "message": {...}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "usage": {...}}}

event: message_stop
data: {"type": "message_stop"}
```

#### `coerce_tool_arguments(arguments, tool_name)`

Normalizes tool call arguments to satisfy Claude Code's Zod schemas:

- Parses JSON strings from code fences (```json)
- Normalizes sub-agent schemas (Agent, Task, Explore)
  - Maps `task`/`query`/`instruction` → `prompt`
  - Removes unsupported keys
- Fixes `TodoWrite` schema (removes `id`, maps `content` → `activeForm`)

### routes.py

FastAPI endpoint definitions.

#### POST `/v1/messages`

Main chat completion endpoint.

**Request Flow:**
1. Extract request body for logging
2. Convert Anthropic → LiteLLM format
3. Route to appropriate provider:
   - `openai/*` → OpenAI-compatible backend
   - `gemini/*` → Google Gemini/Vertex AI
   - Other → Anthropic API
4. Execute request (sync or streaming)
5. Convert response back to Anthropic format

**Model Mapping Logic** (in `models.py:68-103`):
- Haiku/Mini/Flash → `SMALL_MODEL`
- Sonnet/Opus/Pro/GPT-4 → `BIG_MODEL`
- Explicit model names preserved if in `OPENAI_MODELS` or `GEMINI_MODELS`

#### POST `/v1/messages/count_tokens`

Token counting endpoint using LiteLLM's `token_counter`.

#### GET `/v1/models`

Returns available models list (advertising `CLAUDE_MODEL_ALIAS`).

#### GET `/v1/models/{model_id}`

Returns model details.

#### GET `/`

Health check endpoint.

### utils.py

Utility functions for logging and schema handling.

#### `log_request_beautifully(method, path, claude_model, openai_model, num_messages, num_tools, status_code)`

Pretty-prints request logs with color coding:
- Cyan: Claude/Anthropic model name
- Green: Backend model name
- Blue: Message count
- Magenta: Tool count
- Status indicator (green check or red X)

Example output:
```
POST /v1/messages ✓ 200 OK
claude-sonnet-4-5 → gpt-4.1 (2 tools, 5 messages)
```

#### `clean_gemini_schema(schema)`

Recursively removes unsupported JSON schema fields for Gemini:
- `additionalProperties`
- `default`
- Unsupported string formats

#### `append_to_message_log(model_name, messages, tools)`

Logs requests to a JSONL file for auditing (controlled by `APPEND_LOG_MESSAGES`).

#### `MessageFilter`

Custom logging filter to silence LiteLLM/Uvicorn noise.

## Development Setup

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Install dependencies
uv sync

# Run the proxy server
uv run python main.py

# Or run with uvicorn directly
uv run uvicorn app.routes:router --host 0.0.0.0 --port 8083
```

### Development Commands

```bash
# Run tests (if any)
uv run pytest

# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Type check
uv run mypy .
```

## Deployment

### Docker

The proxy runs in Docker as part of the larger deployment system.

```bash
# Using the up.sh wrapper (recommended)
./up.sh proxy-up

# Or directly with docker-compose
docker compose --profile proxy up -d --build
```

### Environment Configuration

Create a `.env` file in the project root:

```env
# Provider selection
PREFERRED_PROVIDER=openai
# PREFERRED_PROVIDER=google

# API Keys
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AI...

# Backend endpoints
OPENAI_BASE_URL=http://qwen3-vllm:8000/v1

# Model configuration
BIG_MODEL=gpt-4.1
SMALL_MODEL=gpt-4.1-mini
CLAUDE_MODEL_ALIAS=claude-sonnet-4-5

# Context window (for vLLM)
VLLM_MAX_CTX=131072
BUFFER_TOKENS=16000

# Logging
APPEND_LOG_MESSAGES=True
MESSAGE_LOG_PATH=messages.jsonl
```

### Environment Variables Reference

| Variable | Provider | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | OpenAI/Gemini | API key for provider |
| `GEMINI_API_KEY` | Gemini | API key for Gemini |
| `ANTHROPIC_API_KEY` | Anthropic | Primary API key |
| `OPENAI_BASE_URL` | OpenAI/vLLM | Custom endpoint URL |
| `VERTEX_PROJECT` | Vertex AI | GCP project ID |
| `VERTEX_LOCATION` | Vertex AI | GCP region |
| `USE_VERTEX_AUTH` | Vertex AI | Use GCP auth instead of API key |

## Integration with Claude Code

Point Claude Code's custom API base to the proxy:

```
http://localhost:8083
```

The proxy will:
1. Accept Anthropic API requests from Claude Code
2. Convert to LiteLLM/OpenAI format
3. Route to local vLLM or GGUF backend (or cloud provider)
4. Convert responses back to Anthropic format
5. Handle streaming responses in real-time

## Debugging

### Enable Debug Logging

```python
# In main.py, change:
logging.basicConfig(level=logging.WARN, ...)
# to:
logging.basicConfig(level=logging.DEBUG, ...)
```

### Common Issues

**Backend unreachable error**
- Check `OPENAI_BASE_URL` is correct
- Verify vLLM server is running
- Ensure network connectivity between proxy and backend

**Tool call schema errors**
- The proxy applies `coerce_tool_arguments()` to normalize schemas
- Check tool names match expected patterns (Agent, Task, Explore, TodoWrite)

**Model mapping issues**
- Check `PREFERRED_PROVIDER` is set correctly
- Verify `BIG_MODEL` and `SMALL_MODEL` are in `OPENAI_MODELS` list
- Use explicit model prefixes: `openai/` or `gemini/`

## Adding New Features

### Adding a New API Endpoint

1. Create route function in `app/routes.py`
2. Add router decorator (`@router.get()`, `@router.post()`, etc.)
3. Import and add to the router in `app/routes.py`

### Adding Support for a New Provider

1. Add configuration variables in `config.py`
2. Add provider routing logic in `routes.py:38-57`
3. Add model prefix in `routes.py:39-41` and `routes.py:49-56`
4. Handle conversion in `converter.py` if needed

### Modifying Tool Schema Coercion

Edit `coerce_tool_arguments()` in `converter.py:35-77`:
- Add new tool names to conditional blocks
- Define allowed keys for each tool type
- Handle schema transformations as needed

## Testing

To add tests:

```python
# tests/test_converter.py
from app.converter import convert_anthropic_to_litellm

def test_model_mapping():
    # Test your conversion logic
    pass
```

Run tests with:
```bash
uv run pytest
```

## Code Style

- Follow PEP 8 conventions
- Use type hints (Pydantic models for validation)
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Use the colorized logging formatter for console output

## License

This project is part of the Qwen deployment system on NVIDIA DGX hardware.
