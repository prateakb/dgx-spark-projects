# Developer Documentation

This document covers development practices, architecture details, and debugging procedures for the qwen-nim-deployment project.

## Project Structure

```
qwen-nim-deployment/
├── proxy_project/              # Claude Code proxy server
│   ├── app/
│   │   ├── config.py          # Environment configuration
│   │   ├── models.py          # Pydantic request/response models
│   │   ├── routes.py          # FastAPI endpoints
│   │   ├── converter.py       # Anthropic↔LiteLLM translation
│   │   └── utils.py           # Logging and utilities
│   ├── main.py                # App entrypoint
│   ├── pyproject.toml         # Python dependencies
│   └── uv.lock                # Dependency lock file
├── spark-vllm-docker/         # vLLM engine source ( submodule )
├── spark-gguf.Dockerfile      # GGUF engine build
├── spark-vllm.Dockerfile      # vLLM engine build
├── claude-proxy.Dockerfile    # Proxy server build
├── docker-compose.yml         # Multi-service orchestration
├── up.sh                      # Development workflow script
└── models/                    # Downloaded GGUF model files
```

## Key Concepts

### Model Routing

The proxy automatically maps Claude model names to backend models based on tier:

| Claude Model Keywords | Backend Mapping |
|----------------------|-----------------|
| haiku, mini, flash   | SMALL_MODEL (e.g., gpt-4.1-mini) |
| sonnet, opus, pro, gpt-4 | BIG_MODEL (e.g., gpt-4.1) |

Models prefixed with `openai/`, `gemini/`, or `anthropic/` preserve the base name unless explicitly mapped.

### Tool Call Schema Coercion

Different LLMs produce tool arguments in slightly different formats. The `coerce_tool_arguments()` function normalizes these to satisfy Claude Code's strict Zod schemas:

- **Agent/Task/Explore**: Maps `task`, `query`, `instruction`, etc. → `prompt`
- **TodoWrite**: Converts `content` → `activeForm`, removes `id` fields
- **JSON strings**: Parses and cleans triple-backtick wrapped JSON

### Streaming Protocol

Claude Code requires specific Server-Sent Events (SSE) format:

1. `message_start` - Message initialization
2. `content_block_start` - Start text block (index 0)
3. `content_block_delta` - Text or JSON chunks
4. `content_block_stop` - Close text block
5. `message_delta` - Usage/update info
6. `message_stop` - Finalize

Tools require new content blocks at indices 1, 2, etc.

## Development Workflow

### Prerequisites

- `uv` for Python dependency management
- Docker and docker-compose for containerized deployment
- NVIDIA container toolkit (for GPU services)

### Local Development

```bash
# Navigate to proxy project
cd proxy_project

# Install dependencies
uv sync

# Run the proxy server
uv run python main.py
```

The server will start on `http://0.0.0.0:8083`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_BASE_URL` | (required) | Backend API endpoint |
| `OPENAI_API_KEY` | `sk-dummy-local-key` | API key for backend |
| `PREFERRED_PROVIDER` | `openai` | Provider type: `openai` or `google` |
| `BIG_MODEL` | `gpt-4.1` | Backend model for large tasks |
| `SMALL_MODEL` | `gpt-4.1-mini` | Backend model for small tasks |
| `CLAUDE_MODEL_ALIAS` | `claude-sonnet-4-6` | Model name advertised to Claude |
| `VLLM_MAX_CTX` | `131072` | Max context window in tokens |
| `BUFFER_TOKENS` | `16000` | Reserve tokens for output |
| `USE_VERTEX_AUTH` | `false` | Enable Vertex AI auth |

### Docker Deployment

```bash
# Start vLLM engine + proxy
./up.sh vllm

# Start GGUF engine + proxy
./up.sh gguf

# Start proxy independently (engine must be running)
./up.sh proxy-up

# View logs
./up.sh logs

# Stop all services
./up.sh down
```

## Debugging

### Common Issues

1. **Connection refused** - Ensure the backend (vLLM/GGUF) is running and `OPENAI_BASE_URL` points to the correct address.

2. **Model not found** - Check that the model identifier matches what your backend serves. Use `/v1/models` to list available models.

3. **Tool call parsing errors** - The proxy attempts automatic coercion, but complex schemas may need manual adjustment in `converter.py:35-77`.

### Logging

The proxy uses a custom `MessageFilter` to suppress LiteLLM noise. Enable debug logging:

```python
# In main.py, change:
logging.basicConfig(level=logging.WARN, ...)
# To:
logging.basicConfig(level=logging.DEBUG, ...)
```

Or set `LOG_LEVEL=DEBUG` in your `.env` file.

## Testing

Run tests with pytest:

```bash
cd proxy_project
uv run pytest
```

### Manual Testing with curl

```bash
# Test health check
curl http://localhost:8083/

# Test message creation
curl -X POST http://localhost:8083/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Test token counting
curl -X POST http://localhost:8083/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Adding New Models

1. Add the model identifier to `OPENAI_MODELS` or `GEMINI_MODELS` in `app/config.py`
2. The proxy will automatically route requests to the new model based on the prefix

## Contributing

1. Create a feature branch
2. Make changes following existing patterns
3. Test with actual Claude Code connections
4. Update this documentation if architecture changes

## License

See individual Dockerfile headers and project files.
