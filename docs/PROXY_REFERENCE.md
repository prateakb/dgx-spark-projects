# Proxy API Reference

Detailed documentation of the Anthropic-compatible proxy API.

## Endpoints

### POST /v1/messages

Create a chat completion.

**Request Headers**:
- `Content-Type: application/json`

**Request Body**:
```json
{
  "model": "claude-sonnet-4-6",
  "messages": [
    {
      "role": "user",
      "content": "Hello"
    }
  ],
  "max_tokens": 1024,
  "stream": false,
  "temperature": 1.0,
  "tools": [],
  "system": "You are a helpful assistant."
}
```

**Response** (non-streaming):
```json
{
  "id": "msg_abc123",
  "type": "message",
  "role": "assistant",
  "model": "claude-sonnet-4-6",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I help you today?"
    }
  ],
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 9
  }
}
```

**Response** (streaming):
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

data: [DONE]
```

### POST /v1/messages/count_tokens

Count tokens in messages.

**Request Body**:
```json
{
  "model": "claude-sonnet-4-6",
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

**Response**:
```json
{
  "input_tokens": 10
}
```

### GET /v1/models

List available models.

**Response**:
```json
{
  "data": [
    {
      "id": "claude-sonnet-4-6",
      "type": "model"
    }
  ]
}
```

### GET /v1/models/{model_id}

Get model details.

**Response**:
```json
{
  "id": "claude-sonnet-4-6",
  "type": "model"
}
```

### GET /

Health check.

**Response**:
```json
{
  "message": "Anthropic Proxy is running (Modular Mode)"
}
```

## Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model name (Claude or backend name) |
| `messages` | array | Yes | Conversation history |
| `max_tokens` | integer | Yes | Maximum output tokens |
| `stream` | boolean | No | Enable streaming (default: false) |
| `temperature` | float | No | Temperature (default: 1.0) |
| `top_p` | float | No | Top-p sampling |
| `top_k` | integer | No | Top-k sampling |
| `tools` | array | No | Function/tool definitions |
| `tool_choice` | object | No | Tool selection |
| `system` | string/array | No | System prompt |
| `stop_sequences` | array | No | Stop sequences |
| `metadata` | object | No | Request metadata |

## Model Naming

### Claude Model Names (Auto-Routed)

| Model Name | Backend |
|------------|---------|
| `claude-3-5-haiku` | `openai/${SMALL_MODEL}` |
| `claude-3-5-sonnet` | `openai/${BIG_MODEL}` |
| `claude-3-opus` | `openai/${BIG_MODEL}` |
| `claude-3.7-sonnet` | `openai/${BIG_MODEL}` |

### Explicit Backend Names

| Prefix | Backend |
|--------|---------|
| `openai/` | OpenAI-compatible (vLLM, local LLM) |
| `gemini/` | Google Gemini/Vertex AI |
| `anthropic/` | Anthropic API |

## Response Format

### MessagesResponse
```json
{
  "id": "string",
  "type": "message",
  "role": "assistant",
  "model": "string",
  "content": [
    {
      "type": "text",
      "text": "string"
    },
    {
      "type": "tool_use",
      "id": "string",
      "name": "string",
      "input": {}
    }
  ],
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

### Usage
```json
{
  "input_tokens": 10,
  "output_tokens": 5,
  "cache_creation_input_tokens": 0,
  "cache_read_input_tokens": 0
}
```

## Tool Calling

Tools follow Anthropic format:

```json
{
  "tools": [
    {
      "name": "Agent",
      "description": "Spawn a sub-agent",
      "input_schema": {
        "type": "object",
        "properties": {
          "prompt": {"type": "string"},
          "run_in_background": {"type": "boolean"}
        }
      }
    }
  ]
}
```

Tool calls are automatically converted to Claude Code-compatible format.

## Error Responses

### 400 Bad Request
Invalid request format.

### 401 Unauthorized
Missing or invalid API key.

### 429 Too Many Requests
Rate limit exceeded.

### 500 Internal Server Error
Backend error or proxy issue.

### 503 Service Unavailable
Backend service not reachable.

## Headers

### Request
- `Content-Type: application/json`

### Response
- `Content-Type: application/json` (or `text/event-stream` for streaming)
