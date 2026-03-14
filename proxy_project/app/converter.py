import json
import uuid
import time
import logging
import litellm
from typing import Any, Dict, List, Union, Optional
from app.models import MessagesResponse, Usage, ContentBlockText, ContentBlockToolUse
from app.utils import clean_gemini_schema
from app.config import VLLM_MAX_CTX, BUFFER_TOKENS

logger = logging.getLogger(__name__)

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
                result += item.get("text", json.dumps(item)) + "\n"
            else:
                result += str(item) + "\n"
        return result.strip()
    if isinstance(content, dict):
        return content.get("text", json.dumps(content))
    return str(content)

def coerce_tool_arguments(arguments: Any, tool_name: str = "") -> Any:
    """Normalizes tool call arguments to satisfy Claude Code's strict Zod schemas."""
    if isinstance(arguments, str):
        try:
            clean_args = arguments.strip()
            if clean_args.startswith("```json"):
                clean_args = clean_args.split("```json")[1].split("```")[0].strip()
            arguments = json.loads(clean_args)
        except json.JSONDecodeError:
            if tool_name in ("Agent", "Explore", "Task"):
                return {"prompt": arguments, "run_in_background": False}
            return {"raw": arguments}

    if not isinstance(arguments, dict):
        return arguments

    # Handle sub-agent schemas
    if tool_name in ("Agent", "Task", "Explore"):
        if "prompt" not in arguments:
            for key in ["task", "query", "instruction", "input", "details", "message"]:
                if key in arguments:
                    arguments["prompt"] = arguments.pop(key)
                    break
        if not arguments.get("prompt"):
            arguments["prompt"] = "Continue based on current context."
        # "description" is required by Claude Code's Task Zod schema — keep it
        if not arguments.get("description"):
            arguments["description"] = arguments.get("prompt", "")[:100]
        allowed_keys = ["description", "prompt", "run_in_background"]
        arguments = {k: v for k, v in arguments.items() if k in allowed_keys}
        arguments["run_in_background"] = False

    # Fix TodoWrite Schema (if applicable)
    if tool_name == "TodoWrite" and isinstance(arguments.get("todos"), list):
        fixed_todos = []
        for item in arguments["todos"]:
            if isinstance(item, dict):
                item.pop("id", None)
                if "activeForm" not in item and "content" in item:
                    item["activeForm"] = item["content"]
                fixed_todos.append(item)
            else:
                fixed_todos.append(item)
        arguments["todos"] = fixed_todos

    return arguments

def convert_anthropic_to_litellm(anthropic_request) -> Dict[str, Any]:
    """Convert Anthropic API request format to LiteLLM format safely."""
    messages = []
    
    # Handle System Prompt
    if anthropic_request.system:
        if isinstance(anthropic_request.system, str):
            messages.append({"role": "system", "content": anthropic_request.system})
        elif isinstance(anthropic_request.system, list):
            system_text = ""
            for block in anthropic_request.system:
                # Use getattr for Pydantic objects, .get() for dicts
                if hasattr(block, 'text'):
                    system_text += block.text + "\n\n"
                elif isinstance(block, dict):
                    system_text += block.get("text", "") + "\n\n"
            if system_text:
                messages.append({"role": "system", "content": system_text.strip()})

    # Handle Conversation Messages
    for msg in anthropic_request.messages:
        content = msg.content
        if isinstance(content, str):
            messages.append({"role": msg.role, "content": content})
        else:
            text_parts = []
            tool_calls_openai = []
            for block in content:
                # Safely extract data regardless of whether block is Dict or Pydantic Object
                is_dict = isinstance(block, dict)
                b_type = block.get('type') if is_dict else getattr(block, 'type', None)
                
                if b_type == "text":
                    b_text = block.get('text', "") if is_dict else getattr(block, 'text', "")
                    text_parts.append(b_text)
                    
                elif b_type == "tool_use":
                    b_id = block.get('id') if is_dict else getattr(block, 'id', None)
                    b_name = block.get('name') if is_dict else getattr(block, 'name', None)
                    b_input = block.get('input', {}) if is_dict else getattr(block, 'input', {})
                    
                    args = b_input if isinstance(b_input, str) else json.dumps(b_input or {})
                    tool_calls_openai.append({
                        "id": b_id,
                        "type": "function",
                        "function": {"name": b_name, "arguments": args}
                    })
                    
                elif b_type == "tool_result":
                    b_tool_use_id = block.get('tool_use_id') if is_dict else getattr(block, 'tool_use_id', None)
                    b_content = block.get('content') if is_dict else getattr(block, 'content', None)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": b_tool_use_id,
                        "content": parse_tool_result_content(b_content)
                    })
            
            # Combine text and tools into the assistant message structure
            if tool_calls_openai or text_parts:
                asst_msg = {"role": msg.role, "content": "\n".join(text_parts) if text_parts else None}
                if tool_calls_openai: 
                    asst_msg["tool_calls"] = tool_calls_openai
                messages.append(asst_msg)

    # Context window logic for OpenAI/vLLM providers
    max_tokens = anthropic_request.max_tokens
    if anthropic_request.model.startswith("openai/"):
        try:
            input_tokens = litellm.token_counter(model="gpt-4", messages=messages)
            input_tokens_adj = int(input_tokens * 1.40)
            available = VLLM_MAX_CTX - input_tokens_adj - BUFFER_TOKENS
            max_tokens = min(max_tokens, max(1, available))
        except:
            pass

    litellm_request = {
        "model": anthropic_request.model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "temperature": anthropic_request.temperature,
        "stream": anthropic_request.stream,
    }

    # Format Tools for OpenAI Function Calling
    if anthropic_request.tools:
        litellm_request["tools"] = []
        for t in anthropic_request.tools:
            # Again, check for Object vs Dict
            t_name = t.get('name') if isinstance(t, dict) else t.name
            t_desc = t.get('description', '') if isinstance(t, dict) else t.description
            t_schema = t.get('input_schema', {}) if isinstance(t, dict) else t.input_schema
            
            litellm_request["tools"].append({
                "type": "function",
                "function": {
                    "name": t_name,
                    "description": t_desc,
                    "parameters": clean_gemini_schema(t_schema) if "gemini" in anthropic_request.model else t_schema
                }
            })

        # Convert Anthropic tool_choice → OpenAI tool_choice so vLLM's parser activates.
        # NOTE: We intentionally never forward "required" — it triggers a vLLM 400 bug
        # with Qwen3 models (github.com/vllm-project/vllm/issues/19051).
        tc = anthropic_request.tool_choice  # Optional[Dict[str, Any]] from Pydantic model
        if not tc:
            litellm_request["tool_choice"] = "auto"
        else:
            tc_type = tc.get("type", "auto")
            if tc_type == "none":
                litellm_request["tool_choice"] = "none"
            elif tc_type == "tool":
                litellm_request["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tc.get("name", "")}
                }
            else:  # "auto" or "any" → always use "auto" to avoid vLLM 400 bugs
                litellm_request["tool_choice"] = "auto"

    return litellm_request

def convert_litellm_to_anthropic(litellm_response, original_request) -> MessagesResponse:
    """Convert LiteLLM (OpenAI format) response to Anthropic API response format."""
    choice = litellm_response.choices[0]
    message = choice.message
    content = []
    
    if message.content:
        content.append(ContentBlockText(type="text", text=message.content))
    
    if hasattr(message, "tool_calls") and message.tool_calls:
        for tc in message.tool_calls:
            content.append(ContentBlockToolUse(
                type="tool_use",
                id=tc.id,
                name=tc.function.name,
                input=coerce_tool_arguments(tc.function.arguments, tc.function.name)
            ))

    stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}
    
    return MessagesResponse(
        id=litellm_response.id,
        model=original_request.model,
        content=content if content else [ContentBlockText(type="text", text="")],
        stop_reason=stop_map.get(choice.finish_reason, "end_turn"),
        usage=Usage(
            input_tokens=litellm_response.usage.prompt_tokens,
            output_tokens=litellm_response.usage.completion_tokens
        )
    )

async def handle_streaming(response_generator, original_request, pre_counted_input_tokens: int = 0):
    """
    Optimized streaming handler that ensures clean transitions 
    between text and tool_use blocks for Claude Code.
    """
    try:
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        
        # 1. Start the Message — use pre-counted input tokens so Claude Code sees real usage
        yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': message_id, 'type': 'message', 'role': 'assistant', 'model': original_request.model, 'content': [], 'usage': {'input_tokens': pre_counted_input_tokens, 'output_tokens': 0}}})}\n\n"
        
        # 2. Start the mandatory Text Block (Index 0)
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

        # State tracking
        text_block_closed = False
        last_anthropic_index = 0 # Index 0 is our text block
        tool_id_map = {}         # Maps OpenAI tool index to Anthropic tool ID
        tool_name_map = {}       # Maps OpenAI tool index to name
        tool_buffer = {}         # Buffers JSON strings
        output_tokens = 0
        input_tokens = 0
        pending_finish_reason = None  # Deferred so the usage-only final chunk can arrive

        async for chunk in response_generator:
            # Always capture usage — vLLM sends it in a no-choices final chunk
            if hasattr(chunk, 'usage') and chunk.usage:
                output_tokens = getattr(chunk.usage, 'completion_tokens', output_tokens)
                input_tokens = getattr(chunk.usage, 'prompt_tokens', input_tokens)

            if not hasattr(chunk, 'choices') or not chunk.choices:
                # This is the usage-only sentinel chunk — flush the deferred finish now
                if pending_finish_reason:
                    break
                continue

            choice = chunk.choices[0]
            delta = getattr(choice, 'delta', {})
            finish_reason = getattr(choice, 'finish_reason', None)

            # --- Text Handling ---
            content_delta = getattr(delta, 'content', None)
            if content_delta:
                if not text_block_closed:
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': content_delta}})}\n\n"

            # --- Tool Call Handling ---
            tool_calls = getattr(delta, 'tool_calls', None)
            if tool_calls:
                # IMPORTANT: If a tool starts, we MUST close the text block (Index 0)
                if not text_block_closed:
                    text_block_closed = True
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

                for tc in tool_calls:
                    idx = getattr(tc, 'index', 0)
                    
                    # New Tool initialization
                    if idx not in tool_id_map:
                        last_anthropic_index += 1
                        t_id = getattr(tc, 'id', f"toolu_{uuid.uuid4().hex[:24]}")
                        t_name = getattr(tc.function, 'name', 'unknown')
                        
                        tool_id_map[idx] = t_id
                        tool_name_map[idx] = t_name
                        tool_buffer[idx] = ""

                        # Start a NEW content block for this tool (Index 1, 2, etc.)
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': last_anthropic_index, 'content_block': {'type': 'tool_use', 'id': t_id, 'name': t_name, 'input': {}}})}\n\n"

                    # Accumulate tool arguments JSON
                    arg_frag = getattr(tc.function, 'arguments', '')
                    if arg_frag:
                        tool_buffer[idx] += arg_frag
                        # We don't send individual tool deltas yet to ensure we can coerce the whole JSON at the end

            # --- Finish Reason ---
            if finish_reason:
                # Close all tool blocks
                for idx in sorted(tool_buffer.keys()):
                    anth_idx = list(tool_buffer.keys()).index(idx) + 1
                    raw_json = tool_buffer.get(idx, "{}")
                    coerced = coerce_tool_arguments(raw_json, tool_name=tool_name_map.get(idx, ""))
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': anth_idx, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(coerced)}})}\n\n"
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': anth_idx})}\n\n"

                if not text_block_closed:
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

                # Defer the final message_delta until usage chunk arrives (or fall through)
                pending_finish_reason = finish_reason

        # Emit final message_delta with real usage (after usage chunk was received)
        finish = pending_finish_reason or "stop"
        stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}
        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_map.get(finish, 'end_turn')}, 'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens}})}\n\n"

        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': str(e)}})}\n\n"