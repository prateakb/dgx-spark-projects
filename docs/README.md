# Qwen NIM Deployment Documentation

This deployment system enables running Qwen models (and other LLMs) locally on NVIDIA DGX hardware, with integration to Claude Code via an Anthropic-compatible API proxy.

## Overview

This project provides:

- **Multiple inference engines**: vLLM (for FP8 models) and llama.cpp (for GGUF models)
- **Claude Code integration**: An Anthropic API proxy that translates requests to LiteLLM-compatible backends
- **Model routing**: Automatic mapping of Claude model names (Sonnet, Haiku, etc.) to backend models
- **Tool call normalization**: Converts tool arguments to satisfy Claude Code's strict schemas

## Quick Start

### Prerequisites

- Docker and docker-compose
- NVIDIA container toolkit (for GPU support)
- Bash shell

### Deployment Options

#### GGUF Engine (llama.cpp)
```bash
./up.sh gguf
```
- Runs `qwen3-coder-gguf` on port 8080
- Uses quantized GGUF models for efficient inference

#### vLLM Engine
```bash
./up.sh vllm
```
- Runs `qwen3-vllm` on port 8000
- Uses FP8 models for high-performance inference

#### Claude Proxy Only
```bash
./up.sh proxy-up
```
- Runs the proxy on port 8083
- Requires a backend (vLLM or GGUF) to be running separately

### Using with Claude Code

Configure Claude Code to use the local proxy:

```
Custom API Base: http://localhost:8083
```

The proxy automatically:
1. Accepts Anthropic API requests
2. Routes to your local backend (vLLM or GGUF)
3. Converts responses back to Anthropic format
4. Handles streaming in real-time

## Directory Structure

```
.
├── docker-compose.yml          # Main deployment configuration
├── docker-compose.qwen3-8b.yml # Alternative config for Qwen3-8B
├── up.sh                       # Deployment helper script
├── proxy_project/              # Claude Code proxy server
│   ├── app/                    # Proxy application code
│   ├── main.py                 # Entry point
│   └── pyproject.toml          # Python dependencies
├── models/                     # Downloaded GGUF models (ignored by git)
└── docs/                       # This documentation
```

## Configuration

Environment variables (`.env` file or docker-compose):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_BASE_URL` | Backend API endpoint | (required) |
| `OPENAI_API_KEY` | API key for backend | `sk-local-spark` |
| `PREFERRED_PROVIDER` | Provider: `openai` or `google` | `openai` |
| `BIG_MODEL` | Backend model for large tasks | `gpt-4.1` |
| `SMALL_MODEL` | Backend model for small tasks | `gpt-4.1-mini` |
| `CLAUDE_MODEL_ALIAS` | Model name for Claude Code | `claude-sonnet-4-6` |
| `VLLM_MAX_CTX` | Max context window (tokens) | `131072` |
| `BUFFER_TOKENS` | Reserve tokens for output | `16000` |

## API Endpoints

The proxy exposes Anthropic-compatible endpoints:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/messages` | Create chat completion |
| POST | `/v1/messages/count_tokens` | Count tokens in messages |
| GET | `/v1/models` | List available models |
| GET | `/v1/models/{model_id}` | Get model details |
| GET | `/` | Health check |

## Model Mapping

The proxy automatically maps Claude model names to backend models:

| Claude Model Keywords | Backend Mapping |
|----------------------|-----------------|
| haiku, mini, flash | SMALL_MODEL |
| sonnet, opus, pro, gpt-4 | BIG_MODEL |

Explicit model names can be used with prefixes:
- `openai/model-name` - Routes to OpenAI-compatible backend
- `gemini/model-name` - Routes to Gemini/Vertex AI

## Stopping Services

```bash
./up.sh down
```

## Logs

```bash
./up.sh logs
```

## Development

See [Developer Guide](DEVELOPER.md) for development setup and code structure.
