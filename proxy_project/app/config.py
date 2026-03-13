import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging Config ---
APPEND_LOG_MESSAGES = os.environ.get("APPEND_LOG_MESSAGES", "True").lower() == "true"
MESSAGE_LOG_PATH = os.environ.get("MESSAGE_LOG_PATH", "messages.jsonl")

# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Vertex AI Configuration
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "unset")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "unset")
USE_VERTEX_AUTH = os.environ.get("USE_VERTEX_AUTH", "False").lower() == "true"

# OpenAI/vLLM Configuration
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
PREFERRED_PROVIDER = os.environ.get("PREFERRED_PROVIDER", "openai").lower()

# Context Window Management
VLLM_MAX_CTX = int(os.environ.get("VLLM_MAX_CTX", "131072"))
BUFFER_TOKENS = int(os.environ.get("BUFFER_TOKENS", "16000"))

# Model Tier Mapping
BIG_MODEL = os.environ.get("BIG_MODEL", "gpt-4.1")
SMALL_MODEL = os.environ.get("SMALL_MODEL", "gpt-4.1-mini")
CLAUDE_MODEL_ALIAS = os.environ.get("CLAUDE_MODEL_ALIAS", "claude-sonnet-4-5")

# Model Validation Lists
OPENAI_MODELS = [
    "o3-mini", "o1", "o1-mini", "o1-pro", "gpt-4.5-preview", 
    "gpt-4o", "gpt-4o-audio-preview", "chatgpt-4o-latest", 
    "gpt-4o-mini", "gpt-4o-mini-audio-preview", "gpt-4.1", "gpt-4.1-mini"
]

# Dynamically add custom models if not in standard list
if BIG_MODEL not in OPENAI_MODELS:
    OPENAI_MODELS.append(BIG_MODEL)
if SMALL_MODEL not in OPENAI_MODELS:
    OPENAI_MODELS.append(SMALL_MODEL)

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]