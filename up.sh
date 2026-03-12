#!/usr/bin/env bash
set -e

echo "========================================================"
echo " DGX Spark Qwen3-Coder-Next Endpoint Setup"
echo "========================================================"

# Default to the stable GGUF profile if no argument is passed
PROFILE=${1:-gguf}

# Tear down existing profiles to free up the proxy port (8083)
echo "Cleaning up any existing containers..."
docker compose --profile '*' down

if [ "$PROFILE" == "gguf" ]; then
    echo "Starting the stable llama.cpp GGUF route + Claude Proxy..."
    
    mkdir -p ./models
    
    MODEL_PATH="./models/Qwen3-Coder-Next-UD-Q4_K_XL.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading Q4 GGUF weights using uv..."
        if ! command -v uv &> /dev/null; then
            echo "Error: 'uv' is not installed. Please install it first."
            exit 1
        fi
        uvx --from huggingface_hub hf download unsloth/Qwen3-Coder-Next-GGUF Qwen3-Coder-Next-UD-Q4_K_XL.gguf --local-dir ./models
    else
        echo "Model found at $MODEL_PATH. Skipping download."
    fi

    echo "Building and launching containers..."
    docker compose --profile gguf up -d --build

    echo "========================================================"
    echo "✅ Success! Stack is online."
    echo "   - Native GGUF API: http://localhost:8080/v1"
    echo "   - Claude Proxy:    http://localhost:8083/v1"

elif [ "$PROFILE" == "vllm" ]; then
    echo "Starting the high-throughput vLLM FP8 route + Claude Proxy..."
    
    echo "Building and launching containers..."
    docker compose --profile vllm up -d --build

    echo "========================================================"
    echo "✅ Success! Stack is online."
    echo "   - Native vLLM API: http://localhost:8000/v1"
    echo "   - Claude Proxy:    http://localhost:8083/v1"

else
    echo "Unknown profile: $PROFILE. Please use 'gguf' or 'vllm'."
    exit 1
fi

echo "To view live inference logs, run: docker compose --profile $PROFILE logs -f"
echo "========================================================"