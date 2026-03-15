# Using with Claude Code

This guide explains how to configure Claude Code to use your local Qwen deployment.

## Configuration

### Step 1: Start the Proxy

```bash
# Option A: Start GGUF + proxy
./up.sh gguf

# Option B: Start vLLM + proxy
./up.sh vllm

# Option C: Start proxy only (if backend already running)
./up.sh proxy-up
```

### Step 2: Configure Claude Code

In Claude Code settings:

1. **API Base**: Set to `http://localhost:8083`
2. **API Key**: Any non-empty string (e.g., `sk-local`)
3. **Model**: Select from available models

The proxy automatically maps Claude model names to your local backend.

### Step 3: Verify Connection

Claude Code should display the configured model. Test with a simple query.

## Model Mapping

The proxy automatically routes Claude model requests:

| Claude Model Requested | Mapped to Backend |
|------------------------|-------------------|
| `claude-3-5-haiku` | `openai/${SMALL_MODEL}` |
| `claude-3-5-sonnet` | `openai/${BIG_MODEL}` |
| `claude-3-opus` | `openai/${BIG_MODEL}` |
| `claude-3.7-sonnet` | `openai/${BIG_MODEL}` |
| `claude-sonnet-4-6` | `openai/${BIG_MODEL}` |

## Tools and Function Calling

The proxy supports Claude Code's tool calling capabilities:

### Supported Tools

- **Agent**: Spawn sub-agents for parallel work
- **Task**: Create task lists
- **Explore**: Search codebases
- **TodoWrite**: Manage to-do lists

### Tool Schema Normalization

The proxy automatically normalizes tool arguments to satisfy Claude Code's strict schemas:

- Maps `task`, `query`, `instruction` → `prompt` for sub-agents
- Converts `content` → `activeForm` for TodoWrite
- Parses JSON from code fence format (```json)

## Streaming

The proxy provides real-time streaming responses with:

- Text deltas as they're generated
- Tool call progress indicators
- Usage statistics in final message delta

## Debugging

### Enable Verbose Logging

Set `LOG_LEVEL=DEBUG` in your `.env` file before starting the proxy.

### Check Proxy Status

```bash
# Health check
curl http://localhost:8083/

# List models
curl http://localhost:8083/v1/models

# Test message
curl -X POST http://localhost:8083/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Common Issues

**Proxy not starting**
- Check port 8083 is not in use
- Verify Docker container is running: `docker compose ps`

**Model not found**
- Check backend is running and accessible
- Verify `OPENAI_BASE_URL` in `.env` matches backend

**Connection refused**
- Backend may not be running
- Check firewall rules
- Verify network configuration in docker-compose

## Advanced Configuration

### Custom Model Names

Edit `docker-compose.yml` to change `CLAUDE_MODEL_ALIAS`:

```yaml
environment:
  - CLAUDE_MODEL_ALIAS=claude-sonnet-4-6
```

### Context Window

Adjust `VLLM_MAX_CTX` and `BUFFER_TOKENS` in `.env`:

```env
VLLM_MAX_CTX=131072
BUFFER_TOKENS=16000
```

The effective context is `VLLM_MAX_CTX - BUFFER_TOKENS - input_tokens`.

## Best Practices

1. **Start with GGUF**: Less GPU memory required, easier to test
2. **Monitor GPU memory**: Use `nvidia-smi` while testing
3. **Use appropriate models**: Haiku/mini for simple tasks, Sonnet for complex
4. **Context management**: Keep input within context window limits
