#!/usr/bin/env bash
set -e

echo "========================================================"
echo " DGX Spark: Modular Endpoint Manager"
echo "========================================================"

# Default variables
PROFILE=${1:-gguf}
MODEL_DIR="./models"
GGUF_MODEL="Qwen3-Coder-Next-UD-Q4_K_XL.gguf"

case $PROFILE in
    # --- ENGINE ACTIONS ---
    "gguf")
        echo ">>> Starting GGUF Engine (llama.cpp)..."
        mkdir -p $MODEL_DIR
        if [ ! -f "$MODEL_DIR/$GGUF_MODEL" ]; then
            uvx --from huggingface_hub hf download unsloth/Qwen3-Coder-Next-GGUF $GGUF_MODEL --local-dir $MODEL_DIR
        fi
        docker compose --profile gguf up -d --build
        echo "✅ GGUF Engine is up at http://localhost:8080"
        ;;

    "vllm")
        echo ">>> Starting vLLM Engine (FP8)..."
        docker compose --profile vllm up -d --build
        echo "✅ vLLM Engine is up at http://localhost:8000"
        ;;

    # --- PROXY ACTIONS ---
    "proxy-up")
        echo ">>> Starting Claude Proxy independently..."
        # We start the proxy profile specifically
        docker compose --profile proxy up -d --build
        echo "✅ Proxy is up at http://localhost:8083"
        ;;

    "proxy-down")
        echo ">>> Stopping Claude Proxy..."
        docker compose stop claude-code-proxy
        ;;

    # --- ZULIP CHANNEL ---
    "zulip")
        echo ">>> Starting Zulip Channel Relay..."
        docker compose -f docker-compose.zulip-channel.yml up -d --build
        echo "✅ Zulip channel is up (check logs with: $0 zulip-logs)"
        ;;

    "zulip-down")
        echo ">>> Stopping Zulip Channel..."
        docker compose -f docker-compose.zulip-channel.yml down
        ;;

    "zulip-logs")
        docker compose -f docker-compose.zulip-channel.yml logs -f
        ;;

    # --- UTILITIES ---
    "down")
        echo ">>> Shutting down EVERYTHING..."
        docker compose --profile '*' down
        docker compose -f docker-compose.zulip-channel.yml down 2>/dev/null || true
        ;;

    "logs")
        docker compose logs -f
        ;;

    *)
        echo "Usage: $0 {gguf | vllm | proxy-up | proxy-down | zulip | zulip-down | zulip-logs | down | logs}"
        exit 1
        ;;
esac

echo "========================================================"