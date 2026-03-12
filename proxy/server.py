from fastapi import FastAPI, Request, HTTPException
import uvicorn
import logging
import json
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Union, Literal
import httpx
import os
from fastapi.responses import JSONResponse, StreamingResponse
import litellm
import uuid
import time
from dotenv import load_dotenv
import re
from datetime import datetime
import sys

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.WARN,  # Change to INFO level to show more details
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Configure uvicorn to be quieter
import uvicorn
# Tell uvicorn's loggers to be quiet
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# Create a filter to block any log messages containing specific strings
class MessageFilter(logging.Filter):
    def filter(self, record):
        # Block messages containing these strings
        blocked_phrases = [
            "LiteLLM completion()",
            "HTTP Request:", 
            "selected model name for cost calculation",
            "utils.py",
            "cost_calculator"
        ]
        
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            for phrase in blocked_phrases:
                if phrase in record.msg:
                    return False
        return True

# Apply the filter to the root logger to catch all messages
root_logger = logging.getLogger()
root_logger.addFilter(MessageFilter())

# Custom formatter for model mapping logs
class ColorizedFormatter(logging.Formatter):
    """Custom formatter to highlight model mappings"""
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    def format(self, record):
        if record.levelno == logging.debug and "MODEL MAPPING" in record.msg:
            # Apply colors and formatting to model mapping logs
            return f"{self.BOLD}{self.GREEN}{record.msg}{self.RESET}"
        return super().format(record)

# Apply custom formatter to console handler
for handler in logger.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.setFormatter(ColorizedFormatter('%(asctime)s - %(levelname)s - %(message)s'))

app = FastAPI()

# Get API keys from environment
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Get Vertex AI project and location from environment (if set)
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "unset")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "unset")

# Option to use Gemini API key instead of ADC for Vertex AI
USE_VERTEX_AUTH = os.environ.get("USE_VERTEX_AUTH", "False").lower() == "true"

# Get OpenAI base URL from environment (if set)
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")

# Get preferred provider (default to openai)
PREFERRED_PROVIDER = os.environ.get("PREFERRED_PROVIDER", "openai").lower()

# Max context window for the currently served vLLM model.
# Set per-model in the Makefile proxy invocation via VLLM_MAX_CTX=<n>.
VLLM_MAX_CTX = int(os.environ.get("VLLM_MAX_CTX", "131072"))
# Safety margin: subtracted from available ctx before capping max_tokens.
# 16000 absorbs the ~10-15K undercount gap between litellm's gpt-4 tokenizer
# and the model-specific VLLM tokenizer on large (80K+) inputs.
BUFFER_TOKENS = int(os.environ.get("BUFFER_TOKENS", "16000"))

# Get model mapping configuration from environment
# Default to latest OpenAI models if not set
BIG_MODEL = os.environ.get("BIG_MODEL", "gpt-4.1")
SMALL_MODEL = os.environ.get("SMALL_MODEL", "gpt-4.1-mini")

# Alias shown to Claude Code in /v1/models. Must contain "sonnet" so Claude Code
# applies the 64K output token limit (vs the lower default for unknown model names).
# Requests using this alias are routed to openai/{BIG_MODEL} / openai/{SMALL_MODEL}
# by the "sonnet" routing rule below, so the vLLM served-model-name is unaffected.
CLAUDE_MODEL_ALIAS = os.environ.get("CLAUDE_MODEL_ALIAS", "claude-sonnet-4-5")

# List of OpenAI models
OPENAI_MODELS = [
    "o3-mini",
    "o1",
    "o1-mini",
    "o1-pro",
    "gpt-4.5-preview",
    "gpt-4o",
    "gpt-4o-audio-preview",
    "chatgpt-4o-latest",
    "gpt-4o-mini",
    "gpt-4o-mini-audio-preview",
    "gpt-4.1",  # Added default big model
    "gpt-4.1-mini", # Added default small model
]
# Dynamically add our local DGX Spark models so they pass validation
if BIG_MODEL not in OPENAI_MODELS:
    OPENAI_MODELS.append(BIG_MODEL)
if SMALL_MODEL not in OPENAI_MODELS:
    OPENAI_MODELS.append(SMALL_MODEL)

# List of Gemini models
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]

# Helper function to clean schema for Gemini
def clean_gemini_schema(schema: Any) -> Any:
    """Recursively removes unsupported fields from a JSON schema for Gemini."""
    if isinstance(schema, dict):
        # Remove specific keys unsupported by Gemini tool parameters
        schema.pop("additionalProperties", None)
        schema.pop("default", None)

        # Check for unsupported 'format' in string types
        if schema.get("type") == "string" and "format" in schema:
            allowed_formats = {"enum", "date-time"}
            if schema["format"] not in allowed_formats:
                logger.debug(f"Removing unsupported format '{schema['format']}' for string type in Gemini schema.")
                schema.pop("format")

        # Recursively clean nested schemas (properties, items, etc.)
        for key, value in list(schema.items()): # Use list() to allow modification during iteration
            schema[key] = clean_gemini_schema(value)
    elif isinstance(schema, list):
        # Recursively clean items in a list
        return [clean_gemini_schema(item) for item in schema]
    return schema

# Models for Anthropic API requests
class ContentBlockText(BaseModel):
    type: Literal["text"]
    text: str

class ContentBlockImage(BaseModel):
    type: Literal["image"]
    source: Dict[str, Any]

class ContentBlockToolUse(BaseModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: Dict[str, Any]

class ContentBlockToolResult(BaseModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]], Dict[str, Any], List[Any], Any]

class SystemContent(BaseModel):
    type: Literal["text"]
    text: str

class Message(BaseModel):
    role: Literal["user", "assistant"] 
    content: Union[str, List[Union[ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult]]]

class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]

class ThinkingConfig(BaseModel):
    enabled: bool = True

class MessagesRequest(BaseModel):
    model: str
    max_tokens: int
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Dict[str, Any]] = None
    thinking: Optional[ThinkingConfig] = None
    original_model: Optional[str] = None  # Will store the original model name
    
    @field_validator('model')
    @classmethod
    def validate_model_field(cls, v: str, info) -> str:
        """
        Validates and maps the incoming model name to the appropriate 
        backend model (Big vs Small) based on the PREFERRED_PROVIDER.
        """
        original_model = v
        new_model = v  # Default to original value
        
        # 1. Clean the model name (remove provider prefixes if present)
        clean_v = v
        if clean_v.startswith('anthropic/'):
            clean_v = clean_v[len('anthropic/'):]
        elif clean_v.startswith('openai/'):
            clean_v = clean_v[len('openai/'):]
        elif clean_v.startswith('gemini/'):
            clean_v = clean_v[len('gemini/'):]
            
        clean_v_lower = clean_v.lower()

        logger.debug(
            f"📋 VALIDATION: Original='{original_model}', "
            f"Provider='{PREFERRED_PROVIDER}', BIG='{BIG_MODEL}', SMALL='{SMALL_MODEL}'"
        )

        # 2. Routing Logic: Map tiers based on keywords
        mapped = False
        
        # --- Mapping Logic --- START ---
        
        # Check for Small Tier keywords (Haiku, Mini, Flash)
        if any(keyword in clean_v_lower for keyword in ['haiku', 'mini', 'flash']):
            if PREFERRED_PROVIDER == "google" and SMALL_MODEL in GEMINI_MODELS:
                new_model = f"gemini/{SMALL_MODEL}"
            else:
                new_model = f"openai/{SMALL_MODEL}"
            mapped = True

        # Check for Big Tier keywords (Sonnet, Opus, Pro, GPT-4, or the Alias itself)
        elif any(keyword in clean_v_lower for keyword in ['sonnet', 'opus', 'pro', 'gpt-4', 'gpt-4.5']):
            if PREFERRED_PROVIDER == "google" and BIG_MODEL in GEMINI_MODELS:
                new_model = f"gemini/{BIG_MODEL}"
            else:
                new_model = f"openai/{BIG_MODEL}"
            mapped = True

        # 3. Fallback: Add prefixes to non-mapped models if they match known lists
        if not mapped:
            if clean_v in GEMINI_MODELS and not v.startswith('gemini/'):
                new_model = f"gemini/{clean_v}"
                mapped = True
            elif clean_v in OPENAI_MODELS and not v.startswith('openai/'):
                new_model = f"openai/{clean_v}"
                mapped = True
                
        # --- Mapping Logic --- END ---

        # 4. Final Logging and State Storage
        if mapped:
            # Use the colorized logger if configured
            logger.debug(f"📌 MODEL MAPPING: '{original_model}' ➡️ '{new_model}'")
        else:
            if not v.startswith(('openai/', 'gemini/', 'anthropic/')):
                logger.warning(f"⚠️ No prefix or mapping rule for model: '{original_model}'. Using as is.")

        # Store the original model in the validation context for later reference in responses
        # (Note: In Pydantic v2, we modify the info.data if available, or just rely on the return)
        if hasattr(info, 'data') and isinstance(info.data, dict):
            info.data['original_model'] = original_model

        return new_model

class TokenCountRequest(BaseModel):
    model: str
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    tools: Optional[List[Tool]] = None
    thinking: Optional[ThinkingConfig] = None
    tool_choice: Optional[Dict[str, Any]] = None
    original_model: Optional[str] = None  # Will store the original model name
    
    @field_validator('model')
    def validate_model_token_count(cls, v, info): # Renamed to avoid conflict
        # Use the same logic as MessagesRequest validator
        # NOTE: Pydantic validators might not share state easily if not class methods
        # Re-implementing the logic here for clarity, could be refactored
        original_model = v
        new_model = v # Default to original value

        logger.debug(f"📋 TOKEN COUNT VALIDATION: Original='{original_model}', Preferred='{PREFERRED_PROVIDER}', BIG='{BIG_MODEL}', SMALL='{SMALL_MODEL}'")

        # Remove provider prefixes for easier matching
        clean_v = v
        if clean_v.startswith('anthropic/'):
            clean_v = clean_v[10:]
        elif clean_v.startswith('openai/'):
            clean_v = clean_v[7:]
        elif clean_v.startswith('gemini/'):
            clean_v = clean_v[7:]

        # --- Mapping Logic --- START ---
        mapped = False
        # Map Haiku to SMALL_MODEL based on provider preference
        if 'haiku' in clean_v.lower():
            if PREFERRED_PROVIDER == "google" and SMALL_MODEL in GEMINI_MODELS:
                new_model = f"gemini/{SMALL_MODEL}"
                mapped = True
            else:
                new_model = f"openai/{SMALL_MODEL}"
                mapped = True

        # Map Sonnet to BIG_MODEL based on provider preference
        elif 'sonnet' in clean_v.lower():
            if PREFERRED_PROVIDER == "google" and BIG_MODEL in GEMINI_MODELS:
                new_model = f"gemini/{BIG_MODEL}"
                mapped = True
            else:
                new_model = f"openai/{BIG_MODEL}"
                mapped = True

        # Add prefixes to non-mapped models if they match known lists
        elif not mapped:
            if clean_v in GEMINI_MODELS and not v.startswith('gemini/'):
                new_model = f"gemini/{clean_v}"
                mapped = True # Technically mapped to add prefix
            elif clean_v in OPENAI_MODELS and not v.startswith('openai/'):
                new_model = f"openai/{clean_v}"
                mapped = True # Technically mapped to add prefix
        # --- Mapping Logic --- END ---

        if mapped:
            logger.debug(f"📌 TOKEN COUNT MAPPING: '{original_model}' ➡️ '{new_model}'")
        else:
             if not v.startswith(('openai/', 'gemini/', 'anthropic/')):
                 logger.warning(f"⚠️ No prefix or mapping rule for token count model: '{original_model}'. Using as is.")
             new_model = v # Ensure we return the original if no rule applied

        # Store the original model in the values dictionary
        values = info.data
        if isinstance(values, dict):
            values['original_model'] = original_model

        return new_model

class TokenCountResponse(BaseModel):
    input_tokens: int

class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

class MessagesResponse(BaseModel):
    id: str
    model: str
    role: Literal["assistant"] = "assistant"
    content: List[Union[ContentBlockText, ContentBlockToolUse]]
    type: Literal["message"] = "message"
    stop_reason: Optional[Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]] = None
    stop_sequence: Optional[str] = None
    usage: Usage

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Get request details
    method = request.method
    path = request.url.path
    
    # Log only basic request details at debug level
    logger.debug(f"Request: {method} {path}")
    
    # Process the request and get the response
    response = await call_next(request)
    
    return response

# Not using validation function as we're using the environment API key

def parse_tool_result_content(content):
    """Helper function to properly parse and normalize tool result content."""
    if content is None:
        return "No content provided"
        
    if isinstance(content, str):
        return content
        
    if isinstance(content, list):
        result = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                result += item.get("text", "") + "\n"
            elif isinstance(item, str):
                result += item + "\n"
            elif isinstance(item, dict):
                if "text" in item:
                    result += item.get("text", "") + "\n"
                else:
                    try:
                        result += json.dumps(item) + "\n"
                    except:
                        result += str(item) + "\n"
            else:
                try:
                    result += str(item) + "\n"
                except:
                    result += "Unparseable content\n"
        return result.strip()
        
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        try:
            return json.dumps(content)
        except:
            return str(content)
            
    # Fallback for any other type
    try:
        return str(content)
    except:
        return "Unparseable content"


def coerce_tool_arguments(arguments: Any, tool_name: str = "") -> Any:
    """
    Normalizes tool call arguments to satisfy Claude Code's strict Zod schemas.
    """
    # 1. Convert string to dict if necessary
    if isinstance(arguments, str):
        try:
            # Handle potential markdown blocks or leading/trailing whitespace
            clean_args = arguments.strip()
            if clean_args.startswith("```json"):
                clean_args = clean_args.split("```json")[1].split("```")[0].strip()
            arguments = json.loads(clean_args)
        except json.JSONDecodeError:
            # Fallback for models that output raw text instead of JSON for tools
            if tool_name in ("Agent", "Explore", "Task"):
                return {"prompt": arguments, "run_in_background": False}
            return {"raw": arguments}

    if not isinstance(arguments, dict):
        return arguments

    # 2. Coerce nested string-encoded JSON (common in Qwen/Llama)
    for k, v in list(arguments.items()):
        if isinstance(v, str) and len(v) > 1 and v[0] in ('[', '{'):
            try:
                arguments[k] = json.loads(v)
            except:
                pass

    # 3. FIX: Sub-agent (Agent/Explore/Task) Schema
    if tool_name in ("Agent", "Task", "Explore"):
        # Map common hallucinations to 'prompt'
        if "prompt" not in arguments:
            for key in ["task", "query", "instruction", "input", "details", "message"]:
                if key in arguments:
                    arguments["prompt"] = arguments.pop(key)
                    break
        
        # Absolute fallback: Claude Code requires a non-empty prompt
        if not arguments.get("prompt"):
            arguments["prompt"] = "Continue based on current context."

        # CRITICAL: Strip any keys NOT in the allowed schema (e.g., 'thought', 'reasoning')
        # Zod validation in the CLI will fail if unknown keys are present.
        allowed_keys = ["prompt", "run_in_background"]
        arguments = {k: v for k, v in arguments.items() if k in allowed_keys}
        
        # Force synchronous execution so the CLI doesn't lose the task ID
        arguments["run_in_background"] = False

    # 4. FIX: TodoWrite Schema
    if tool_name == "TodoWrite" and isinstance(arguments.get("todos"), list):
        fixed_todos = []
        for item in arguments["todos"]:
            if isinstance(item, dict):
                item.pop("id", None) # Remove hallucinated IDs
                if "activeForm" not in item and "content" in item:
                    item["activeForm"] = item["content"]
                fixed_todos.append(item)
            else:
                fixed_todos.append(item)
        arguments["todos"] = fixed_todos

    return arguments



def convert_anthropic_to_litellm(anthropic_request: MessagesRequest) -> Dict[str, Any]:
    """Convert Anthropic API request format to LiteLLM format (which follows OpenAI)."""
    # LiteLLM already handles Anthropic models when using the format model="anthropic/claude-3-opus-20240229"
    # So we just need to convert our Pydantic model to a dict in the expected format
    
    messages = []
    
    # Add system message if present
    if anthropic_request.system:
        # Handle different formats of system messages
        if isinstance(anthropic_request.system, str):
            # Simple string format
            messages.append({"role": "system", "content": anthropic_request.system})
        elif isinstance(anthropic_request.system, list):
            # List of content blocks
            system_text = ""
            for block in anthropic_request.system:
                if hasattr(block, 'type') and block.type == "text":
                    system_text += block.text + "\n\n"
                elif isinstance(block, dict) and block.get("type") == "text":
                    system_text += block.get("text", "") + "\n\n"
            
            if system_text:
                messages.append({"role": "system", "content": system_text.strip()})
    
    # Add conversation messages
    for idx, msg in enumerate(anthropic_request.messages):
        content = msg.content
        if isinstance(content, str):
            messages.append({"role": msg.role, "content": content})
        else:
            # Special handling for tool_result in user messages.
            # Convert Anthropic tool_result blocks → OpenAI {"role":"tool"} messages
            # so vLLM's chat template can apply <tool_response> wrapping correctly.
            if msg.role == "user" and any(block.type == "tool_result" for block in content if hasattr(block, "type")):
                # Emit any leading text block as a regular user message first
                leading_text = ""
                for block in content:
                    if hasattr(block, "type") and block.type == "text":
                        leading_text += block.text + "\n"

                if leading_text.strip():
                    messages.append({"role": "user", "content": leading_text.strip()})

                # Emit each tool_result as a proper OpenAI tool message
                for block in content:
                    if not hasattr(block, "type") or block.type != "tool_result":
                        continue

                    tool_id = block.tool_use_id if hasattr(block, "tool_use_id") else ""

                    # Flatten content to a plain string
                    result_content = ""
                    if hasattr(block, "content"):
                        if isinstance(block.content, str):
                            result_content = block.content
                        elif isinstance(block.content, list):
                            for content_block in block.content:
                                if hasattr(content_block, "type") and content_block.type == "text":
                                    result_content += content_block.text + "\n"
                                elif isinstance(content_block, dict) and content_block.get("type") == "text":
                                    result_content += content_block.get("text", "") + "\n"
                                elif isinstance(content_block, dict):
                                    result_content += content_block.get("text", json.dumps(content_block)) + "\n"
                        elif isinstance(block.content, dict):
                            result_content = block.content.get("text", json.dumps(block.content))
                        else:
                            result_content = str(block.content)

                    # Proper OpenAI tool message — vLLM renders this as <tool_response>
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result_content.strip(),
                    })

            else:
                # Regular handling for other message types.
                # Assistant messages with tool_use blocks must be converted to
                # OpenAI tool_calls format (not content blocks) so litellm/vLLM
                # can serialise them correctly.
                text_parts = []
                tool_calls_openai = []
                for block in content:
                    if hasattr(block, "type"):
                        if block.type == "text":
                            text_parts.append(block.text)
                        elif block.type == "image":
                            # images stay as content blocks
                            text_parts.append("[image]")
                        elif block.type == "tool_use":
                            # Convert Anthropic tool_use → OpenAI tool_calls entry
                            arguments = block.input if isinstance(block.input, str) else json.dumps(block.input or {})
                            tool_calls_openai.append({
                                "id": block.id,
                                "type": "function",
                                "function": {
                                    "name": block.name,
                                    "arguments": arguments,
                                },
                            })

                if tool_calls_openai:
                    # Build OpenAI-format assistant message with tool_calls
                    asst_msg: Dict[str, Any] = {"role": "assistant"}
                    if text_parts:
                        asst_msg["content"] = "\n".join(text_parts)
                    else:
                        asst_msg["content"] = None
                    asst_msg["tool_calls"] = tool_calls_openai
                    messages.append(asst_msg)
                else:
                    # Plain assistant text message
                    messages.append({"role": msg.role, "content": "\n".join(text_parts) if text_parts else ""})

    
    # For local vLLM models, cap max_tokens dynamically based on remaining context.
    # vLLM rejects requests where max_tokens > (max_seq_len - input_tokens).
    # The gpt-4 tokenizer underestimates Qwen token counts by ~40% on code-heavy
    # inputs (Qwen uses smaller tokens). Multiply the estimate by 1.40 to compensate
    # before computing available headroom.
    max_tokens = anthropic_request.max_tokens
    if anthropic_request.model.startswith("openai/"):
        try:
            input_tokens = litellm.token_counter(model="gpt-4", messages=messages)
            if input_tokens <= 0:
                raise ValueError("zero count")
        except Exception:
            # Fallback: rough estimate (~4 chars per token)
            input_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 4
        # Scale gpt-4 token estimate up to approximate Qwen token count
        input_tokens_adj = int(input_tokens * 1.40)
        available = VLLM_MAX_CTX - input_tokens_adj - BUFFER_TOKENS
        hard_cap = max(256, int(VLLM_MAX_CTX * 0.9))  # allow up to 90% of ctx for output (large refactors/diffs)
        max_tokens = min(max_tokens, max(1, available), hard_cap)
        logger.debug(f"max_tokens={max_tokens} (gpt4_est={input_tokens}, qwen_adj={input_tokens_adj}, ctx={VLLM_MAX_CTX}, requested={anthropic_request.max_tokens})")
    
    # Create LiteLLM request dict
    litellm_request = {
        "model": anthropic_request.model,  # it understands "anthropic/claude-x" format
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "temperature": anthropic_request.temperature,
        "stream": anthropic_request.stream,
    }

    # Only include thinking field for Anthropic models
    if anthropic_request.thinking and anthropic_request.model.startswith("anthropic/"):
        litellm_request["thinking"] = anthropic_request.thinking

    # Add optional parameters if present
    if anthropic_request.stop_sequences:
        litellm_request["stop"] = anthropic_request.stop_sequences
    
    if anthropic_request.top_p:
        litellm_request["top_p"] = anthropic_request.top_p
    
    if anthropic_request.top_k:
        litellm_request["top_k"] = anthropic_request.top_k
    
    # Convert tools to OpenAI format
    if anthropic_request.tools:
        openai_tools = []
        is_gemini_model = anthropic_request.model.startswith("gemini/")

        for tool in anthropic_request.tools:
            # Convert to dict if it's a pydantic model
            if hasattr(tool, 'dict'):
                tool_dict = tool.dict()
            else:
                # Ensure tool_dict is a dictionary, handle potential errors if 'tool' isn't dict-like
                try:
                    tool_dict = dict(tool) if not isinstance(tool, dict) else tool
                except (TypeError, ValueError):
                     logger.error(f"Could not convert tool to dict: {tool}")
                     continue # Skip this tool if conversion fails

            # Clean the schema if targeting a Gemini model
            input_schema = tool_dict.get("input_schema", {})
            if is_gemini_model:
                 logger.debug(f"Cleaning schema for Gemini tool: {tool_dict.get('name')}")
                 input_schema = clean_gemini_schema(input_schema)

            # Create OpenAI-compatible function tool
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool_dict["name"],
                    "description": tool_dict.get("description", ""),
                    "parameters": input_schema # Use potentially cleaned schema
                }
            }
            openai_tools.append(openai_tool)

        litellm_request["tools"] = openai_tools
    
    # Convert tool_choice to OpenAI format if present
    if anthropic_request.tool_choice:
        if hasattr(anthropic_request.tool_choice, 'dict'):
            tool_choice_dict = anthropic_request.tool_choice.dict()
        else:
            tool_choice_dict = anthropic_request.tool_choice
            
        # Handle Anthropic's tool_choice format
        choice_type = tool_choice_dict.get("type")
        if choice_type == "auto":
            litellm_request["tool_choice"] = "auto"
        elif choice_type == "any":
            litellm_request["tool_choice"] = "any"
        elif choice_type == "tool" and "name" in tool_choice_dict:
            litellm_request["tool_choice"] = {
                "type": "function",
                "function": {"name": tool_choice_dict["name"]}
            }
        else:
            # Default to auto if we can't determine
            litellm_request["tool_choice"] = "auto"
    
    return litellm_request

def convert_litellm_to_anthropic(litellm_response: Union[Dict[str, Any], Any], 
                                 original_request: MessagesRequest) -> MessagesResponse:
    """Convert LiteLLM (OpenAI format) response to Anthropic API response format."""
    
    # Enhanced response extraction with better error handling
    try:
        # Get the clean model name to check capabilities
        clean_model = original_request.model
        if clean_model.startswith("anthropic/"):
            clean_model = clean_model[len("anthropic/"):]
        elif clean_model.startswith("openai/"):
            clean_model = clean_model[len("openai/"):]
        
        # Check if this is a Claude model (which supports content blocks)
        is_claude_model = clean_model.startswith("claude-")
        
        # Handle ModelResponse object from LiteLLM
        if hasattr(litellm_response, 'choices') and hasattr(litellm_response, 'usage'):
            # Extract data from ModelResponse object directly
            choices = litellm_response.choices
            message = choices[0].message if choices and len(choices) > 0 else None
            content_text = message.content if message and hasattr(message, 'content') else ""
            tool_calls = message.tool_calls if message and hasattr(message, 'tool_calls') else None
            finish_reason = choices[0].finish_reason if choices and len(choices) > 0 else "stop"
            usage_info = litellm_response.usage
            response_id = getattr(litellm_response, 'id', f"msg_{uuid.uuid4()}")
        else:
            # For backward compatibility - handle dict responses
            # If response is a dict, use it, otherwise try to convert to dict
            try:
                response_dict = litellm_response if isinstance(litellm_response, dict) else litellm_response.dict()
            except AttributeError:
                # If .dict() fails, try to use model_dump or __dict__ 
                try:
                    response_dict = litellm_response.model_dump() if hasattr(litellm_response, 'model_dump') else litellm_response.__dict__
                except AttributeError:
                    # Fallback - manually extract attributes
                    response_dict = {
                        "id": getattr(litellm_response, 'id', f"msg_{uuid.uuid4()}"),
                        "choices": getattr(litellm_response, 'choices', [{}]),
                        "usage": getattr(litellm_response, 'usage', {})
                    }
                    
            # Extract the content from the response dict
            choices = response_dict.get("choices", [{}])
            message = choices[0].get("message", {}) if choices and len(choices) > 0 else {}
            content_text = message.get("content", "")
            tool_calls = message.get("tool_calls", None)
            finish_reason = choices[0].get("finish_reason", "stop") if choices and len(choices) > 0 else "stop"
            usage_info = response_dict.get("usage", {})
            response_id = response_dict.get("id", f"msg_{uuid.uuid4()}")
        
        # Create content list for Anthropic format
        content = []
        
        # Add text content block if present (text might be None or empty for pure tool call responses)
        if content_text is not None and content_text != "":
            content.append({"type": "text", "text": content_text})
        
        # Add tool calls if present — always convert to Anthropic tool_use blocks
        # (regardless of whether the upstream model is Claude or an OpenAI-compat model)
        if tool_calls:
            logger.debug(f"Processing tool calls: {tool_calls}")
            
            # Convert to list if it's not already
            if not isinstance(tool_calls, list):
                tool_calls = [tool_calls]
                
            for idx, tool_call in enumerate(tool_calls):
                logger.debug(f"Processing tool call {idx}: {tool_call}")
                
                # Extract function data based on whether it's a dict or object
                if isinstance(tool_call, dict):
                    function = tool_call.get("function", {})
                    tool_id = tool_call.get("id", f"tool_{uuid.uuid4()}")
                    name = function.get("name", "")
                    arguments = function.get("arguments", "{}")
                else:
                    function = getattr(tool_call, "function", None)
                    tool_id = getattr(tool_call, "id", f"tool_{uuid.uuid4()}")
                    name = getattr(function, "name", "") if function else ""
                    arguments = getattr(function, "arguments", "{}") if function else "{}"
                
                # Convert string arguments to dict if needed
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool arguments as JSON: {arguments}")
                        arguments = {"raw": arguments}

                # Normalise arguments: coerce string-encoded arrays/objects,
                # fix TodoWrite activeForm/id issues (see coerce_tool_arguments).
                arguments = coerce_tool_arguments(arguments, tool_name=name)
                
                logger.debug(f"Adding tool_use block: id={tool_id}, name={name}, input={arguments}")
                
                content.append({
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name,
                    "input": arguments
                })
        
        # Get usage information - extract values safely from object or dict
        if isinstance(usage_info, dict):
            prompt_tokens = usage_info.get("prompt_tokens", 0)
            completion_tokens = usage_info.get("completion_tokens", 0)
        else:
            prompt_tokens = getattr(usage_info, "prompt_tokens", 0)
            completion_tokens = getattr(usage_info, "completion_tokens", 0)
        
        # Map OpenAI finish_reason to Anthropic stop_reason
        stop_reason = None
        if finish_reason == "stop":
            stop_reason = "end_turn"
        elif finish_reason == "length":
            stop_reason = "max_tokens"
        elif finish_reason == "tool_calls":
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"  # Default
        
        # Make sure content is never empty
        if not content:
            content.append({"type": "text", "text": ""})
        
        # Create Anthropic-style response
        anthropic_response = MessagesResponse(
            id=response_id,
            model=original_request.model,
            role="assistant",
            content=content,
            stop_reason=stop_reason,
            stop_sequence=None,
            usage=Usage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens
            )
        )
        
        return anthropic_response
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        error_message = f"Error converting response: {str(e)}\n\nFull traceback:\n{error_traceback}"
        logger.error(error_message)
        
        # In case of any error, create a fallback response
        return MessagesResponse(
            id=f"msg_{uuid.uuid4()}",
            model=original_request.model,
            role="assistant",
            content=[{"type": "text", "text": f"Error converting response: {str(e)}. Please check server logs."}],
            stop_reason="end_turn",
            usage=Usage(input_tokens=0, output_tokens=0)
        )

async def handle_streaming(response_generator, original_request: MessagesRequest):
    try:
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        
        # 1. Initial Start Event
        start_data = {
            'type': 'message_start',
            'message': {
                'id': message_id, 'type': 'message', 'role': 'assistant',
                'model': original_request.model, 'content': [],
                'stop_reason': None, 'stop_sequence': None,
                'usage': {'input_tokens': 0, 'output_tokens': 0}
            }
        }
        yield f"event: message_start\ndata: {json.dumps(start_data)}\n\n"
        
        # 2. Open initial content block for text
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

        tool_index = None
        tool_content_by_index = {}
        tool_name_by_index = {}
        tool_id_by_index = {}
        last_anthropic_index = 0
        
        accumulated_text = ""
        text_sent = False
        text_block_closed = False
        input_tokens = 0
        output_tokens = 0
        final_usage_sent = False

        async for chunk in response_generator:
            # Capture usage if present
            if hasattr(chunk, 'usage') and chunk.usage:
                input_tokens = getattr(chunk.usage, 'prompt_tokens', input_tokens)
                output_tokens = getattr(chunk.usage, 'completion_tokens', output_tokens)

            if not hasattr(chunk, 'choices') or not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = getattr(choice, 'delta', {})
            finish_reason = getattr(choice, 'finish_reason', None)

            # --- Text Handling ---
            content_delta = getattr(delta, 'content', None)
            if content_delta:
                accumulated_text += content_delta
                if not text_block_closed:
                    text_sent = True
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': content_delta}})}\n\n"

            # --- Tool Call Handling ---
            tool_calls = getattr(delta, 'tool_calls', None)
            if tool_calls:
                # Close text block before starting tools
                if not text_block_closed:
                    text_block_closed = True
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

                for tc in tool_calls:
                    idx = getattr(tc, 'index', 0)
                    
                    if idx not in tool_id_by_index:
                        # New Tool Start
                        last_anthropic_index += 1
                        t_id = getattr(tc, 'id', f"toolu_{uuid.uuid4().hex[:24]}")
                        t_name = getattr(tc.function, 'name', '')
                        
                        tool_id_by_index[idx] = t_id
                        tool_name_by_index[idx] = t_name
                        tool_content_by_index[idx] = ""
                        
                        # Use last_anthropic_index to keep content block sequence linear
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': last_anthropic_index, 'content_block': {'type': 'tool_use', 'id': t_id, 'name': t_name, 'input': {}}})}\n\n"

                    # Buffer the JSON fragments
                    arg_frag = getattr(tc.function, 'arguments', '')
                    if arg_frag:
                        tool_content_by_index[idx] += arg_frag

            # --- Finish Handling ---
            if finish_reason:
                # 1. Close all open tool blocks with COERCED arguments
                for idx in sorted(tool_id_by_index.keys()):
                    anth_idx = list(tool_id_by_index.keys()).index(idx) + 1
                    raw_json = tool_content_by_index.get(idx, "{}")
                    
                    # Apply the fixes
                    coerced = coerce_tool_arguments(raw_json, tool_name=tool_name_by_index.get(idx, ""))
                    
                    # Send the final coerced JSON as one delta
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': anth_idx, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(coerced)}})}\n\n"
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': anth_idx})}\n\n"

                # 2. Ensure text block is closed
                if not text_block_closed:
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

                # 3. Final Message Delta with Usage
                stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}
                yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_map.get(finish_reason, 'end_turn'), 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"
                final_usage_sent = True
                break

        if not final_usage_sent:
            yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': output_tokens}})}\n\n"

        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': str(e)}})}\n\n"

@app.post("/v1/messages")
async def create_message(
    request: MessagesRequest,
    raw_request: Request
):
    try:
        body = await raw_request.body()
        body_json = json.loads(body.decode('utf-8'))
        original_model = body_json.get("model", "unknown")
        
        display_model = original_model
        if "/" in display_model:
            display_model = display_model.split("/")[-1]
        
        logger.debug(f"📊 PROCESSING REQUEST: Model={request.model}, Stream={request.stream}")
        
        # 1. Translate Anthropic structure to OpenAI JSON structure
        litellm_request = convert_anthropic_to_litellm(request)
        
        # 2. Determine which API key and routing to use
        if request.model.startswith("openai/"):
            litellm_request["api_key"] = OPENAI_API_KEY if OPENAI_API_KEY else "sk-dummy-local-key"
            litellm_request["custom_llm_provider"] = "openai"
            
            if OPENAI_BASE_URL:
                litellm_request["api_base"] = OPENAI_BASE_URL
        elif request.model.startswith("gemini/"):
            if USE_VERTEX_AUTH:
                litellm_request["vertex_project"] = VERTEX_PROJECT
                litellm_request["vertex_location"] = VERTEX_LOCATION
                litellm_request["custom_llm_provider"] = "vertex_ai"
            else:
                litellm_request["api_key"] = GEMINI_API_KEY
        else:
            litellm_request["api_key"] = ANTHROPIC_API_KEY

        # ====================================================================
        # 🔥 THE FIX: The massive 120-line 'OpenAI limitation' block that was 
        # flattening tool calls into plaintext has been entirely deleted from here.
        # Now, pure native tool_calls pass directly to llama.cpp/vLLM.
        # ====================================================================
        
        logger.debug(f"Request for model: {litellm_request.get('model')}, stream: {litellm_request.get('stream', False)}")
        
        # 3. Fire the request
        if request.stream:
            num_tools = len(request.tools) if request.tools else 0
            
            log_request_beautifully(
                "POST", raw_request.url.path, display_model, 
                litellm_request.get('model'), len(litellm_request['messages']), 
                num_tools, 200
            )
            response_generator = await litellm.acompletion(**litellm_request)
            
            return StreamingResponse(
                handle_streaming(response_generator, request),
                media_type="text/event-stream"
            )
        else:
            num_tools = len(request.tools) if request.tools else 0
            
            log_request_beautifully(
                "POST", raw_request.url.path, display_model, 
                litellm_request.get('model'), len(litellm_request['messages']), 
                num_tools, 200
            )
            start_time = time.time()
            litellm_response = litellm.completion(**litellm_request)
            logger.debug(f"✅ RESPONSE RECEIVED: Model={litellm_request.get('model')}, Time={time.time() - start_time:.2f}s")
            
            anthropic_response = convert_litellm_to_anthropic(litellm_response, request)
            return anthropic_response
                
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        
        error_details = {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": error_traceback
        }
        
        for attr in ['message', 'status_code', 'response', 'llm_provider', 'model']:
            if hasattr(e, attr):
                error_details[attr] = getattr(e, attr)
        
        if hasattr(e, '__dict__'):
            for key, value in e.__dict__.items():
                if key not in error_details and key not in ['args', '__traceback__']:
                    error_details[key] = str(value)
        
        def sanitize_for_json(obj):
            if isinstance(obj, dict):
                return {k: sanitize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_for_json(item) for item in obj]
            elif hasattr(obj, '__dict__'):
                return sanitize_for_json(obj.__dict__)
            elif hasattr(obj, 'text'):
                return str(obj.text)
            else:
                try:
                    json.dumps(obj)
                    return obj
                except (TypeError, ValueError):
                    return str(obj)
        
        sanitized_details = sanitize_for_json(error_details)
        logger.error(f"Error processing request: {json.dumps(sanitized_details, indent=2)}")
        
        error_message = f"Error: {str(e)}"
        if 'message' in error_details and error_details['message']:
            error_message += f"\nMessage: {error_details['message']}"
        if 'response' in error_details and error_details['response']:
            error_message += f"\nResponse: {error_details['response']}"
        
        status_code = error_details.get('status_code', 500)
        raise HTTPException(status_code=status_code, detail=error_message)

@app.get("/v1/models")
async def list_models():
    """Anthropic-format model list. Claude Code queries this to determine output token limits."""
    models = [_model_info(CLAUDE_MODEL_ALIAS)]
    # deduplicate while preserving order
    seen = set()
    unique = []
    for m in models:
        if m["id"] not in seen:
            seen.add(m["id"])
            unique.append(m)
    return {"data": unique}

@app.get("/v1/models/{model_id:path}")
async def get_model(model_id: str):
    """Anthropic-format single model lookup. Claude Code queries this on startup."""
    return _model_info(model_id)


@app.post("/v1/messages/count_tokens")
async def count_tokens(
    request: TokenCountRequest,
    raw_request: Request
):
    try:
        # Log the incoming token count request
        original_model = request.original_model or request.model
        
        # Get the display name for logging, just the model name without provider prefix
        display_model = original_model
        if "/" in display_model:
            display_model = display_model.split("/")[-1]
        
        # Clean model name for capability check
        clean_model = request.model
        if clean_model.startswith("anthropic/"):
            clean_model = clean_model[len("anthropic/"):]
        elif clean_model.startswith("openai/"):
            clean_model = clean_model[len("openai/"):]
        
        # Convert the messages to a format LiteLLM can understand
        converted_request = convert_anthropic_to_litellm(
            MessagesRequest(
                model=request.model,
                max_tokens=100,  # Arbitrary value not used for token counting
                messages=request.messages,
                system=request.system,
                tools=request.tools,
                tool_choice=request.tool_choice,
                thinking=request.thinking
            )
        )
        
        # Use LiteLLM's token_counter function
        try:
            # Import token_counter function
            from litellm import token_counter
            
            # Log the request beautifully
            num_tools = len(request.tools) if request.tools else 0
            
            log_request_beautifully(
                "POST",
                raw_request.url.path,
                display_model,
                converted_request.get('model'),
                len(converted_request['messages']),
                num_tools,
                200  # Assuming success at this point
            )
            
            # Prepare token counter arguments
            token_counter_args = {
                "model": converted_request["model"],
                "messages": converted_request["messages"],
                "custom_llm_provider": "openai"  # CRITICAL FIX: Explicitly force the OpenAI protocol
            }
            
            # Add custom base URL for OpenAI models if configured
            if request.model.startswith("openai/") and OPENAI_BASE_URL:
                token_counter_args["api_base"] = OPENAI_BASE_URL
            
            # Count tokens
            token_count = token_counter(**token_counter_args)
            
            # Return Anthropic-style response
            return TokenCountResponse(input_tokens=token_count)
            
        except ImportError:
            logger.error("Could not import token_counter from litellm")
            # Fallback to a simple approximation
            return TokenCountResponse(input_tokens=1000)  # Default fallback
            
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error counting tokens: {str(e)}\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Error counting tokens: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Anthropic Proxy for LiteLLM"}

# Define ANSI color codes for terminal output
class Colors:
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"
def log_request_beautifully(method, path, claude_model, openai_model, num_messages, num_tools, status_code):
    """Log requests in a beautiful, twitter-friendly format showing Claude to OpenAI mapping."""
    # Format the Claude model name nicely
    claude_display = f"{Colors.CYAN}{claude_model}{Colors.RESET}"
    
    # Extract endpoint name
    endpoint = path
    if "?" in endpoint:
        endpoint = endpoint.split("?")[0]
    
    # Extract just the OpenAI model name without provider prefix
    openai_display = openai_model
    if "/" in openai_display:
        openai_display = openai_display.split("/")[-1]
    openai_display = f"{Colors.GREEN}{openai_display}{Colors.RESET}"
    
    # Format tools and messages
    tools_str = f"{Colors.MAGENTA}{num_tools} tools{Colors.RESET}"
    messages_str = f"{Colors.BLUE}{num_messages} messages{Colors.RESET}"
    
    # Format status code
    status_str = f"{Colors.GREEN}✓ {status_code} OK{Colors.RESET}" if status_code == 200 else f"{Colors.RED}✗ {status_code}{Colors.RESET}"
    

    # Put it all together in a clear, beautiful format
    log_line = f"{Colors.BOLD}{method} {endpoint}{Colors.RESET} {status_str}"
    model_line = f"{claude_display} → {openai_display} {tools_str} {messages_str}"
    
    # Print to console
    print(log_line)
    print(model_line)
    sys.stdout.flush()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Run with: uvicorn server:app --reload --host 0.0.0.0 --port 8083")
        sys.exit(0)
    
    # Configure uvicorn to run with minimal logs
    uvicorn.run(app, host="0.0.0.0", port=8083, log_level="error")