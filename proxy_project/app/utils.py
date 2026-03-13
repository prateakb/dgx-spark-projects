import logging
import json
import sys
from typing import Any
import datetime

def append_to_message_log(model_name, messages, tools=None):
    """Appends the request details to a local JSONL file for auditing."""
    from app.config import APPEND_LOG_MESSAGES, MESSAGE_LOG_PATH
    
    if not APPEND_LOG_MESSAGES:
        return

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model": model_name,
        "message_count": len(messages),
        "messages": messages, # This stores the full conversation
        "tools_provided": [t.name for t in tools] if tools else []
    }

    try:
        with open(MESSAGE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Failed to write to message log: {e}")
        
# Configure a custom filter to silence LiteLLM/Uvicorn noise
class MessageFilter(logging.Filter):
    def filter(self, record):
        # Block messages containing these strings to keep console clean
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

class ColorizedFormatter(logging.Formatter):
    """Custom formatter to highlight model mappings in the logs"""
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    def format(self, record):
        if record.levelno == logging.DEBUG and "MODEL MAPPING" in record.msg:
            return f"{self.BOLD}{self.GREEN}{record.msg}{self.RESET}"
        return super().format(record)

def clean_gemini_schema(schema: Any) -> Any:
    """Recursively removes unsupported fields from a JSON schema for Gemini."""
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        schema.pop("default", None)

        if schema.get("type") == "string" and "format" in schema:
            allowed_formats = {"enum", "date-time"}
            if schema["format"] not in allowed_formats:
                schema.pop("format")

        for key, value in list(schema.items()):
            schema[key] = clean_gemini_schema(value)
    elif isinstance(schema, list):
        return [clean_gemini_schema(item) for item in schema]
    return schema

class Colors:
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

def log_request_beautifully(method, path, claude_model, openai_model, num_messages, num_tools, status_code):
    """Log requests in a clean format showing the mapping from Claude/Anthropic to Backend."""
    claude_display = f"{Colors.CYAN}{claude_model}{Colors.RESET}"
    
    endpoint = path.split("?")[0] if "?" in path else path
    
    openai_display = openai_model.split("/")[-1] if "/" in openai_model else openai_model
    openai_display = f"{Colors.GREEN}{openai_display}{Colors.RESET}"
    
    tools_str = f"{Colors.MAGENTA}{num_tools} tools{Colors.RESET}"
    messages_str = f"{Colors.BLUE}{num_messages} messages{Colors.RESET}"
    
    status_str = (f"{Colors.GREEN}✓ {status_code} OK{Colors.RESET}" 
                  if status_code == 200 
                  else f"{Colors.RED}✗ {status_code}{Colors.RESET}")
    
    log_line = f"{Colors.BOLD}{method} {endpoint}{Colors.RESET} {status_str}"
    model_line = f"{claude_display} → {openai_display} ({tools_str}, {messages_str})"
    
    print(log_line)
    print(model_line)
    sys.stdout.flush()