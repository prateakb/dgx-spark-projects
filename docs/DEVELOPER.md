# Development Guide

Information for developers working on the proxy and deployment system.

## Project Structure

```
proxy_project/
├── app/
│   ├── __init__.py
│   ├── config.py        # Configuration loading
│   ├── models.py        # Pydantic models
│   ├── routes.py        # FastAPI endpoints
│   ├── converter.py     # API translation layer
│   └── utils.py         # Utilities and logging
├── main.py              # Application entry point
├── pyproject.toml       # Dependencies
└── README.md
```

## Development Setup

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Navigate to proxy project
cd proxy_project

# Install dependencies
uv sync

# Run the proxy server
uv run python main.py
```

The server will start on `http://0.0.0.0:8083`.

## Development Commands

```bash
# Run tests
uv run pytest

# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Type check
uv run mypy .
```

## Core Components

### config.py

Environment-based configuration loader.

**Key Functions**:
- `load_dotenv()` - Load `.env` file
- Model validation lists (OPENAI_MODELS, GEMINI_MODELS)

**Environment Variables**:
- `PREFERRED_PROVIDER` - Provider selection
- `BIG_MODEL` / `SMALL_MODEL` - Backend model names
- `VLLM_MAX_CTX` - Context window size

### models.py

Pydantic models for request/response validation.

**Request Models**:
- `MessagesRequest` - Main chat completion request
- `TokenCountRequest` - Token counting request

**Response Models**:
- `MessagesResponse` - Anthropic-compatible response
- `TokenCountResponse` - Token count result
- `Usage` - Token usage statistics

**Content Block Models**:
- `ContentBlockText` - Text content
- `ContentBlockToolUse` - Tool call
- `ContentBlockToolResult` - Tool result

### converter.py

API format translation layer.

**Key Functions**:

#### `convert_anthropic_to_litellm(request)`

Converts Anthropic request to LiteLLM format:
1. Handles system prompts
2. Converts content blocks to OpenAI format
3. Transforms tool_use to tool_calls
4. Applies context window limits
5. Formats tools for OpenAI function calling

#### `convert_litellm_to_anthropic(response, original_request)`

Converts LiteLLM response to Anthropic format:
1. Maps finish reasons
2. Converts tool_calls to tool_use blocks
3. Applies schema coercion

#### `handle_streaming(response_generator, original_request)`

Generates Anthropic-compatible streaming events:
1. `message_start` - Initialize message
2. `content_block_start` - Start text block
3. `content_block_delta` - Text/JSON chunks
4. `content_block_stop` - Close block
5. `message_delta` - Usage info
6. `message_stop` - Finalize

#### `coerce_tool_arguments(arguments, tool_name)`

Normalizes tool arguments:
- Parses JSON from code fences
- Normalizes sub-agent schemas (Agent, Task, Explore)
- Fixes TodoWrite schema

### routes.py

FastAPI endpoint handlers.

#### POST `/v1/messages`

Main chat completion endpoint.

**Request Flow**:
1. Extract body for logging
2. Convert Anthropic → LiteLLM
3. Route to provider (openai/gemini/anthropic)
4. Execute request (sync or streaming)
5. Convert response back to Anthropic format

#### POST `/v1/messages/count_tokens`

Token counting using LiteLLM's `token_counter`.

#### GET `/v1/models`

Returns available models list.

#### GET `/`

Health check endpoint.

### utils.py

Utility functions.

**Key Functions**:

#### `log_request_beautifully(...)`

Pretty-prints request logs:
- Cyan: Claude model name
- Green: Backend model name
- Blue: Message count
- Magenta: Tool count

#### `clean_gemini_schema(schema)`

Removes unsupported JSON schema fields for Gemini.

#### `MessageFilter`

Custom logging filter to suppress LiteLLM noise.

## Adding New Features

### Add New API Endpoint

```python
# app/routes.py
@router.get("/new-endpoint")
async def new_endpoint():
    return {"message": "New endpoint"}
```

### Add New Provider Support

1. Add configuration in `config.py`
2. Add routing in `routes.py:38-57`
3. Add model prefixes
4. Handle conversion in `converter.py`

### Modify Tool Schema

Edit `coerce_tool_arguments()` in `converter.py:35-77`:
```python
if tool_name == "NewTool":
    # Add schema transformations
```

## Debugging

### Enable Debug Logging

Change in `main.py`:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

### Common Issues

**Backend unreachable**
- Check `OPENAI_BASE_URL` is correct
- Verify backend is running
- Check network connectivity

**Tool call schema errors**
- Check tool names match expected patterns
- Verify schema in `coerce_tool_arguments()`

**Model mapping issues**
- Check `PREFERRED_PROVIDER` setting
- Verify models in `OPENAI_MODELS` list

## Testing

### Manual Testing with curl

```bash
# Health check
curl http://localhost:8083/

# Test message
curl -X POST http://localhost:8083/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Count tokens
curl -X POST http://localhost:8083/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Code Style

- Follow PEP 8 conventions
- Use type hints (Pydantic models)
- Log at appropriate levels
- Use colorized logging for console output

## Pull Request Checklist

- [ ] Code follows style guide
- [ ] Type hints included
- [ ] Logging added for new flows
- [ ] Manual testing completed
- [ ] Documentation updated if needed
