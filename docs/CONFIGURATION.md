# Configuration Guide

Detailed information about configuring the Qwen NIM deployment.

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_BASE_URL` | Backend API endpoint | `http://qwen3-vllm:8000/v1` |

### Provider Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `PREFERRED_PROVIDER` | Provider type: `openai` or `google` | `openai` |
| `OPENAI_API_KEY` | API key for OpenAI-compatible backends | `sk-local-spark` |
| `GEMINI_API_KEY` | API key for Google Gemini | `None` |
| `ANTHROPIC_API_KEY` | API key for Anthropic API | `None` |

### Backend Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_MAX_CTX` | Maximum context window (tokens) | `131072` |
| `BUFFER_TOKENS` | Reserve tokens for output | `16000` |

### Model Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BIG_MODEL` | Backend model for large models | `gpt-4.1` |
| `SMALL_MODEL` | Backend model for small models | `gpt-4.1-mini` |
| `CLAUDE_MODEL_ALIAS` | Model name advertised to Claude Code | `claude-sonnet-4-6` |

### Google Vertex AI Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `VERTEX_PROJECT` | GCP project ID | `unset` |
| `VERTEX_LOCATION` | GCP region | `unset` |
| `USE_VERTEX_AUTH` | Use GCP auth instead of API key | `false` |

### Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `APPEND_LOG_MESSAGES` | Enable message logging | `true` |
| `MESSAGE_LOG_PATH` | Path to JSONL log file | `messages.jsonl` |

## .env File Example

```env
# Backend Configuration
OPENAI_BASE_URL=http://qwen3-vllm:8000/v1

# Provider Configuration
PREFERRED_PROVIDER=openai
OPENAI_API_KEY=sk-local-spark

# Model Configuration
BIG_MODEL=Qwen3-Coder-Next
SMALL_MODEL=Qwen3-Coder-Next
CLAUDE_MODEL_ALIAS=claude-sonnet-4-6

# Context Window
VLLM_MAX_CTX=131072
BUFFER_TOKENS=16000

# Logging
APPEND_LOG_MESSAGES=true
MESSAGE_LOG_PATH=messages.jsonl
```

## docker-compose.yml Configuration

### vLLM Service

```yaml
qwen3-vllm:
  image: scitrera/dgx-spark-vllm:0.14.0-t4
  container_name: qwen3-coder-vllm
  profiles: ["vllm"]
  runtime: nvidia
  ipc: host
  restart: unless-stopped
  ports:
    - "8000:8000"
  volumes:
    - ~/.cache/huggingface:/root/.cache/huggingface
  command: >
    vllm serve Qwen/Qwen3-Coder-Next-FP8
    --host 0.0.0.0
    --port 8000
    --dtype auto
    --kv-cache-dtype fp8
    --gpu-memory-utilization 0.9
    --max-model-len 131072
    --trust-remote-code
    --enable-auto-tool-choice
    --tool-call-parser qwen3_coder
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

### GGUF Service

```yaml
qwen3-coder-gguf:
  build:
    context: .
    dockerfile: llama-server-gguf.Dockerfile
  profiles: ["gguf"]
  ulimits:
    memlock:
      soft: -1
      hard: -1
  volumes:
    - ./models:/models
  ports:
    - "8080:8080"
  environment:
    - CUDA_VISIBLE_DEVICES=0
    - NCCL_IB_DISABLE=1
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  command: >
    --model /models/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf
    --port 8080
    --host 0.0.0.0
    --alias Qwen3-Coder-Next
    -ngl 999
    -fa on
    --no-mmap
    --mlock
    --numa distribute
    --ctx-size 131072
    --cache-type-k q4_0
    --cache-type-v q4_0
    --batch-size 4096
    --ubatch-size 1024
    --threads 20
    --parallel 2
    --cont-batching
    --override-kv "tokenizer.ggml.max_context_length=int:131072"
```

### Proxy Service

```yaml
claude-proxy:
  build:
    context: .
    dockerfile: claude-proxy.Dockerfile
  container_name: claude-code-proxy
  profiles: ["proxy"]
  restart: unless-stopped
  ports:
    - "8083:8083"
  environment:
    - HOST=0.0.0.0
    - PORT=8083
    - PREFERRED_PROVIDER=openai
    - VLLM_MAX_CTX=65536
    - OPENAI_BASE_URL=http://qwen3-8b:8080/v1
    - OPENAI_API_KEY=sk-local-spark
    - BIG_MODEL=qwen3-coder
    - SMALL_MODEL=qwen3-coder
```

## Model Routing Rules

The proxy automatically maps Claude model names:

| Claude Model | Mapping Logic | Backend |
|--------------|---------------|---------|
| haiku, mini, flash | SMALL_MODEL keyword | `openai/${SMALL_MODEL}` |
| sonnet, opus, pro, gpt-4 | BIG_MODEL keyword | `openai/${BIG_MODEL}` |
| o3, o1, o1-mini | Explicit match | `openai/{model}` |
| gemini-* | Explicit match | `gemini/{model}` |

## Context Window Management

### vLLM Configuration

```env
VLLM_MAX_CTX=131072
BUFFER_TOKENS=16000
```

Effective output capacity:
```
Available Output = VLLM_MAX_CTX - BUFFER_TOKENS - Input Tokens
```

### GGUF Configuration

```env
VLLM_MAX_CTX=32768  # or 65536, 131072
BUFFER_TOKENS=16000
```

## Provider-Specific Configuration

### OpenAI/VLLM Backend

```env
PREFERRED_PROVIDER=openai
OPENAI_BASE_URL=http://qwen3-vllm:8000/v1
OPENAI_API_KEY=sk-local-spark
```

### Gemini Backend

```env
PREFERRED_PROVIDER=google
GEMINI_API_KEY=AI...
BIG_MODEL=gemini-2.5-flash
SMALL_MODEL=gemini-2.5-flash
```

### Vertex AI Backend

```env
PREFERRED_PROVIDER=google
USE_VERTEX_AUTH=true
VERTEX_PROJECT=your-gcp-project
VERTEX_LOCATION=us-central1
```

## Docker Compose Environments

### Development

```yaml
environment:
  - LOG_LEVEL=DEBUG
```

### Production

```yaml
environment:
  - LOG_LEVEL=INFO
  - APPEND_LOG_MESSAGES=false
```

## Network Configuration

### Bridge Network

```yaml
networks:
  qwen3-8b-net:
    driver: bridge
```

### Custom Network

```yaml
networks:
  internal:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.20.0.0/24
```
