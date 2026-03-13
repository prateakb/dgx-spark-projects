from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import litellm
import json
import logging
import time
from typing import Union

# Import modular components
from app.models import MessagesRequest, TokenCountRequest, TokenCountResponse
from app.converter import (
    convert_anthropic_to_litellm, 
    convert_litellm_to_anthropic, 
    handle_streaming
)
from app.utils import log_request_beautifully
from app.config import (
    OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY,
    OPENAI_BASE_URL, USE_VERTEX_AUTH, VERTEX_PROJECT, VERTEX_LOCATION,
    CLAUDE_MODEL_ALIAS
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/v1/messages")
async def create_message(request: MessagesRequest, raw_request: Request):
    try:
        # 1. Extraction for logging
        body = await raw_request.body()
        body_json = json.loads(body.decode('utf-8'))
        original_model = body_json.get("model", "unknown")
        display_model = original_model.split("/")[-1] if "/" in original_model else original_model
        
        # 2. Convert Anthropic -> LiteLLM
        litellm_request = convert_anthropic_to_litellm(request)
        
        # 3. Provider Routing & Auth
        if request.model.startswith("openai/"):
            litellm_request["api_key"] = OPENAI_API_KEY or "sk-dummy-local-key"
            litellm_request["custom_llm_provider"] = "openai"
            
            if OPENAI_BASE_URL:
                # Strip the prefix for local NIM/vLLM backends
                litellm_request["model"] = litellm_request["model"].replace("openai/", "")
                litellm_request["api_base"] = OPENAI_BASE_URL
                logger.info(f"🔗 Routing to custom backend: {OPENAI_BASE_URL}")
                
        elif request.model.startswith("gemini/"):
            if USE_VERTEX_AUTH:
                litellm_request["vertex_project"] = VERTEX_PROJECT
                litellm_request["vertex_location"] = VERTEX_LOCATION
                litellm_request["custom_llm_provider"] = "vertex_ai"
            else:
                litellm_request["api_key"] = GEMINI_API_KEY
        else:
            litellm_request["api_key"] = ANTHROPIC_API_KEY

        # FIX: Define num_tools early so it's available for logging in both branches
        num_tools = len(request.tools) if request.tools else 0
        
        # 4. Execute Request
        if request.stream:
            log_request_beautifully(
                "POST", raw_request.url.path, display_model, 
                litellm_request.get('model'), len(litellm_request['messages']), 
                num_tools, 200
            )
            # Added a timeout to prevent hanging on GPU warmup
            response_generator = await litellm.acompletion(**litellm_request, timeout=600)
            
            return StreamingResponse(
                handle_streaming(response_generator, request),
                media_type="text/event-stream"
            )
        else:
            log_request_beautifully(
                "POST", raw_request.url.path, display_model, 
                litellm_request.get('model'), len(litellm_request['messages']), 
                num_tools, 200
            )
            start_time = time.time()
            litellm_response = litellm.completion(**litellm_request, timeout=600)
            
            logger.debug(f"✅ RESPONSE RECEIVED: {time.time() - start_time:.2f}s")
            return convert_litellm_to_anthropic(litellm_response, request)
                
    except Exception as e:
        # Check if it's a connection error to provide a better hint
        err_str = str(e)
        if "Connection error" in err_str or "APIConnectionError" in err_str:
            logger.error(f"❌ Could not connect to backend at {OPENAI_BASE_URL}. Check if your NIM/vLLM server is running.")
            raise HTTPException(status_code=503, detail=f"Backend unreachable at {OPENAI_BASE_URL}")
        
        logger.error(f"Error processing request: {err_str}", exc_info=True)
        raise HTTPException(status_code=getattr(e, 'status_code', 500), detail=err_str)

@router.post("/v1/messages/count_tokens")
async def count_tokens(request: TokenCountRequest, raw_request: Request):
    try:
        original_model = request.original_model or request.model
        display_model = original_model.split("/")[-1] if "/" in original_model else original_model
        
        converted_request = convert_anthropic_to_litellm(
            MessagesRequest(
                model=request.model,
                max_tokens=100,
                messages=request.messages,
                system=request.system,
                tools=request.tools
            )
        )
        
        from litellm import token_counter
        num_tools = len(request.tools) if request.tools else 0
        log_request_beautifully("POST", raw_request.url.path, display_model, converted_request.get('model'), len(converted_request['messages']), num_tools, 200)
        
        token_count = token_counter(
            model=converted_request["model"],
            messages=converted_request["messages"],
            custom_llm_provider="openai"
        )
        return TokenCountResponse(input_tokens=token_count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/models")
async def list_models():
    return {"data": [{"id": CLAUDE_MODEL_ALIAS, "type": "model"}]}

@router.get("/v1/models/{model_id:path}")
async def get_model(model_id: str):
    return {"id": model_id, "type": "model"}

@router.get("/")
async def root():
    return {"message": "Modular Anthropic Proxy is Online"}