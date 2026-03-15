# Deployment Guide

This guide covers deploying the Qwen NIM deployment system using Docker Compose.

## System Requirements

- Docker 24+ with docker-compose plugin
- NVIDIA container toolkit (for GPU acceleration)
- At least 16GB RAM (varies by model size)
- GPU with CUDA support (for vLLM) or any GPU (for GGUF)

## Quick Deployment

### Using the Helper Script

```bash
# Start GGUF engine (recommended for most users)
./up.sh gguf

# Start vLLM engine (for FP8 models)
./up.sh vllm

# Start proxy independently (requires backend)
./up.sh proxy-up

# Stop all services
./up.sh down

# View logs
./up.sh logs
```

### Manual Docker Compose Commands

```bash
# GGUF engine
docker compose --profile gguf up -d

# vLLM engine
docker compose --profile vllm up -d

# Proxy only
docker compose --profile proxy up -d

# Stop all services
docker compose --profile '*' down
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Backend endpoint (must match your running service)
OPENAI_BASE_URL=http://qwen3-vllm:8000/v1
# OR for GGUF:
# OPENAI_BASE_URL=http://qwen3-coder-gguf:8080/v1

# API key (dummy for local backends)
OPENAI_API_KEY=sk-local-spark

# Provider selection
PREFERRED_PROVIDER=openai

# Model configuration
BIG_MODEL=Qwen3-Coder-Next
SMALL_MODEL=Qwen3-Coder-Next
CLAUDE_MODEL_ALIAS=claude-sonnet-4-6

# Context window
VLLM_MAX_CTX=131072
BUFFER_TOKENS=16000
```

### Model Download

For GGUF models, the `up.sh gguf` script automatically downloads the model:
- Default: `Qwen3-Coder-Next-UD-Q4_K_XL.gguf`
- Location: `./models/` directory

You can manually download models:
```bash
uvx --from huggingface_hub hf download unsloth/Qwen3-Coder-Next-GGUF <filename> --local-dir ./models
```

## Docker Compose Profiles

### gguf Profile

Runs the llama.cpp server with quantized GGUF models.

**Container**: `qwen3-coder-gguf`
**Port**: 8080

**Features**:
- Multi-GPU support via `--parallel`
- Memory locking (`--mlock`)
- NUMA distribution (`--numa distribute`)
- Large context support (131K tokens)
- KV cache quantization

### vllm Profile

Runs vLLM with FP8 models.

**Container**: `qwen3-vllm`
**Port**: 8000

**Features**:
- FP8 quantization for efficiency
- Auto tool choice support
- Custom tool call parser
- High GPU memory utilization

### proxy Profile

Runs the Claude Code proxy server.

**Container**: `claude-code-proxy`
**Port**: 8083

**Features**:
- Anthropic API compatibility
- Model routing
- Tool call normalization
- Streaming support

## Network Configuration

By default, services communicate via Docker Compose networking. The proxy container accesses backend services by name:
- `qwen3-vllm:8000` for vLLM
- `qwen3-coder-gguf:8080` for GGUF

For external access to the proxy:
- Port 8083 is exposed on localhost
- Configure Claude Code with `http://localhost:8083`

## Troubleshooting

### Container won't start

Check logs:
```bash
docker compose logs <service-name>
```

Common issues:
- **Port already in use**: Stop existing containers or change port mapping
- **Missing model files**: Run `./up.sh gguf` to download models
- **GPU not detected**: Install NVIDIA container toolkit

### Connection refused errors

Verify backend is running:
```bash
# Test vLLM
curl http://localhost:8000/v1/models

# Test GGUF
curl http://localhost:8080/v1/models
```

### Proxy can't reach backend

Check network connectivity:
```bash
docker compose exec claude-code-proxy ping qwen3-vllm
```

Or use the correct service name in `OPENAI_BASE_URL`:
```env
# For vLLM
OPENAI_BASE_URL=http://qwen3-vllm:8000/v1

# For GGUF
OPENAI_BASE_URL=http://qwen3-coder-gguf:8080/v1
```

## Advanced Configuration

### Custom Models

Modify `docker-compose.yml` to use different models:

```yaml
qwen3-coder-gguf:
  command: >
    --model /models/your-custom-model-Q4_K_M.gguf
    --port 8080
    --alias YourCustomModel
```

### Multi-GPU Setup

Add parallel workers for GGUF:
```yaml
qwen3-coder-gguf:
  command: >
    --model /models/model.gguf
    --port 8080
    --parallel 4  # Adjust based on GPU count
```

### Resource Limits

```yaml
qwen3-coder-gguf:
  deploy:
    resources:
      limits:
        memory: 16G
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

## Cleanup

Stop and remove all containers:
```bash
docker compose --profile '*' down
```

Remove volumes (deletes downloaded models):
```bash
docker volume prune
rm -rf ./models/
```
