import logging
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Union, Literal

# Import the configuration constants for validation logic
from app.config import (
    PREFERRED_PROVIDER, BIG_MODEL, SMALL_MODEL, 
    OPENAI_MODELS, GEMINI_MODELS
)

logger = logging.getLogger(__name__)

# --- Anthropic Style Content Blocks ---

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

# --- Requests ---

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
    original_model: Optional[str] = None
    
    @field_validator('model')
    @classmethod
    def validate_model_field(cls, v: str, info) -> str:
        original_model = v
        new_model = v
        
        clean_v = v
        if clean_v.startswith(('anthropic/', 'openai/', 'gemini/')):
            clean_v = clean_v.split('/', 1)[1]
            
        clean_v_lower = clean_v.lower()
        mapped = False
        
        # Routing Logic
        if any(keyword in clean_v_lower for keyword in ['haiku', 'mini', 'flash']):
            new_model = f"gemini/{SMALL_MODEL}" if PREFERRED_PROVIDER == "google" else f"openai/{SMALL_MODEL}"
            mapped = True
        elif any(keyword in clean_v_lower for keyword in ['sonnet', 'opus', 'pro', 'gpt-4', 'gpt-4.5']):
            new_model = f"gemini/{BIG_MODEL}" if PREFERRED_PROVIDER == "google" else f"openai/{BIG_MODEL}"
            mapped = True

        if not mapped:
            if clean_v in GEMINI_MODELS and not v.startswith('gemini/'):
                new_model = f"gemini/{clean_v}"
            elif clean_v in OPENAI_MODELS and not v.startswith('openai/'):
                new_model = f"openai/{clean_v}"
                
        if mapped:
            logger.debug(f"📌 MODEL MAPPING: '{original_model}' ➡️ '{new_model}'")

        if info.data and isinstance(info.data, dict):
            info.data['original_model'] = original_model
        elif hasattr(info, 'context') and isinstance(info.context, dict):
            info.context['original_model'] = original_model
            
        return new_model

class TokenCountRequest(BaseModel):
    model: str
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    tools: Optional[List[Tool]] = None
    thinking: Optional[ThinkingConfig] = None
    tool_choice: Optional[Dict[str, Any]] = None
    original_model: Optional[str] = None

# --- Responses ---

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

class TokenCountResponse(BaseModel):
    input_tokens: int