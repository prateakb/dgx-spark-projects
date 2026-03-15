# Architecture Guide

This document describes the system architecture and how components interact.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code                              │
│                  (Anthropic API Client)                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Anthropic Proxy (app/)                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI Server (port 8083)                              │  │
│  │  - /v1/messages                                          │  │
│  │  - /v1/messages/count_tokens                             │  │
│  │  - /v1/models                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                         │                                       │
│  ┌──────────────────────▼──────────────────────┐               │
│  │  Anthropic ↔ LiteLLM Converter             │               │
│  │  - convert_anthropic_to_litellm()          │               │
│  │  - convert_litellm_to_anthropic()          │               │
│  │  - handle_streaming()                      │               │
│  └──────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend Services                           │
│                                                                 │
│  ┌─────────────────────┐         ┌─────────────────────┐      │
│  │  vLLM (port 8000)   │         │  llama.cpp (8080)   │      │
│  │  - FP8 quantized    │         │  - GGUF quantized   │      │
│  │  - OpenAI-compatible│         │  - OpenAI-compatible│      │
│  └─────────────────────┘         └─────────────────────┘      │
│                                                                 │
│  ┌─────────────────────┐         ┌─────────────────────┐      │
│  │  OpenAI API         │         │  Gemini API         │      │
│  └─────────────────────┘         └─────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### Proxy Application (proxy_project/app/)

#### config.py
Environment-based configuration loader:
- Loads variables from `.env` file
- Defines provider-specific settings
- Configures context window limits
- Maintains model name validation lists

#### models.py
Pydantic models for API validation:
- **Requests**: `MessagesRequest`, `TokenCountRequest`
- **Responses**: `MessagesResponse`, `TokenCountResponse`, `Usage`
- **Content blocks**: `ContentBlockText`, `ContentBlockToolUse`, `ContentBlockToolResult`
- **Model validation**: Automatic Claude model name mapping to backend models

#### routes.py
FastAPI endpoint handlers:
- `POST /v1/messages`: Main chat completion
- `POST /v1/messages/count_tokens`: Token counting
- `GET /v1/models`: List available models
- `GET /`: Health check

#### converter.py
API format translation layer:
- `convert_anthropic_to_litellm()`: Anthropic → OpenAI/LiteLLM
- `convert_litellm_to_anthropic()`: OpenAI/LiteLLM → Anthropic
- `handle_streaming()`: SSE event generation
- `coerce_tool_arguments()`: Schema normalization

#### utils.py
Utility functions:
- `log_request_beautifully()`: Colorized request logging
- `clean_gemini_schema()`: Schema cleanup for Gemini
- `MessageFilter`: Logging filter to suppress noise

## Data Flow

### Request Flow

1. **Claude Code** sends Anthropic API request
2. **Proxy** receives request at `/v1/messages`
3. **Model validation** in `routes.py`:
   - Maps Claude model name to backend model
   - Logs the mapping
4. **Conversion** in `converter.py`:
   - Anthropic format → LiteLLM/OpenAI format
   - Tools converted to function calls
   - Content blocks flattened to message roles
5. **Provider routing** in `routes.py`:
   - `openai/*` → OpenAI-compatible backend
   - `gemini/*` → Google Gemini/Vertex AI
   - Other → Anthropic API
6. **Backend execution** via LiteLLM
7. **Response conversion** back to Anthropic format
8. **Streaming** (if requested): Anthropic SSE events

### Streaming Flow

1. Request has `stream: true`
2. Proxy initiates async call to backend
3. Each chunk from backend processed:
   - Text deltas sent as `content_block_delta`
   - Tool calls trigger new `content_block_start`
   - Finish reason triggers `message_delta`
4. Final `message_stop` event
5. Client receives clean SSE stream

### Tool Call Flow

1. Model outputs tool call in OpenAI format:
   ```json
   {
     "tool_calls": [{
       "id": "tool_123",
       "function": {"name": "Agent", "arguments": "..."}
     }]
   }
   ```
2. Proxy converts to Anthropic format:
   ```json
   {
     "content": [{
       "type": "tool_use",
       "id": "tool_123",
       "name": "Agent",
       "input": {...}
     }]
   }
   ```
3. `coerce_tool_arguments()` normalizes schema:
   - Maps sub-agent fields
   - Fixes TodoWrite structure
   - Parses JSON strings
4. Claude Code receives normalized schema

## Profile Structure

### GGUF Profile
- **Image**: Custom `llama-server-gguf.Dockerfile`
- **Base**: CUDA 12.1 runtime
- **Build**: Compiles llama.cpp with CUDA support
- **Runtime**: Runs `llama-server` with optimized flags
- **Memory**: Uses memory locking and NUMA distribution

### vLLM Profile
- **Image**: `scitrera/dgx-spark-vllm:0.14.0-t4`
- **Base**: CUDA 12.6
- **Configuration**: FP8 quantization, auto tool choice
- **GPU**: Full utilization with 0.9 memory budget

### Proxy Profile
- **Image**: Custom `claude-proxy.Dockerfile`
- **Base**: Python 3.11 slim
- **Dependencies**: FastAPI, LiteLLM, uvicorn
- **Port**: 8083 exposed on host

## Network Configuration

Docker Compose networking:
- Services communicate by container name
- Proxy uses `http://qwen3-vllm:8000` for vLLM
- Proxy uses `http://qwen3-coder-gguf:8080` for GGUF
- Host access via port mapping (8083)

## Scaling Considerations

### GGUF
- CPU-only inference possible
- GPU acceleration recommended
- Memory usage ~4 bytes per token (Q4_K_M)
- Parallel workers via `--parallel` flag

### vLLM
- GPU-only (CUDA)
- FP8 quantization (1 byte per token)
- High GPU memory utilization
- Context window up to 131K tokens
