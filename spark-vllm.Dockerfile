# spark-vllm.Dockerfile

# --------------------------------------------------------
# Use NVIDIA's heavily optimized PyTorch ARM64 base image
# This contains the correct CUDA drivers for Grace Blackwell
# --------------------------------------------------------
FROM nvcr.io/nvidia/pytorch:24.03-py3

WORKDIR /workspace

# Install uv for lightning-fast package resolution
RUN pip install uv

# Install vLLM directly from PyPI's native aarch64 wheels. 
# This completely bypasses the broken source-compilation stage you hit.
# We also ensure transformers is up to date for Qwen3 support.
RUN uv pip install --system vllm>=0.7.0 transformers>=4.40.0 accelerate

# Expose the API port
EXPOSE 8000

# Start the OpenAI-compatible API server
ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]