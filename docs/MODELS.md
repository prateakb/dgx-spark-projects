# Models Guide

Information about available models and how to use them.

## Model Types

### vLLM Models (FP8)

| Model | Format | GPU Memory | Notes |
|-------|--------|------------|-------|
| Qwen3-Coder-Next-FP8 | FP8 | ~24GB | High performance, NVIDIA NVFP4 |

### GGUF Models (Quantized)

| Quantization | File Pattern | GPU Memory | CPU Memory | Use Case |
|--------------|--------------|------------|------------|----------|
| Q2_K | *Q2_K*.gguf | ~8GB | ~8GB | Minimal VRAM |
| Q3_K | *Q3_K*.gguf | ~10GB | ~12GB | Low VRAM |
| Q4_K_M | *Q4_K_M*.gguf | ~16GB | ~18GB | Balanced |
| Q5_K_M | *Q5_K_M*.gguf | ~20GB | ~22GB | High quality |
| Q6_K | *Q6_K*.gguf | ~24GB | ~26GB | Near-FP16 quality |
| Q8_0 | *Q8_0*.gguf | ~32GB | ~34GB | Lossless |

### Model Mapping

| Model Name | Provider | Backend |
|------------|----------|---------|
| openai/Qwen3-Coder-Next | openai | vLLM (FP8) |
| openai/Qwen3.5-122B-A10B-Q4_K_M | openai | GGUF (Q4_K_M) |
| gemini/Qwen3.5-122B-A10B-Q4_K_M | gemini | GGUF (Q4_K_M) |

## Deployment Options

### Using vLLM (FP8)

```bash
./up.sh vllm
```

Configuration in `docker-compose.yml`:
```yaml
qwen3-vllm:
  image: scitrera/dgx-spark-vllm:0.14.0-t4
  command: >
    vllm serve Qwen/Qwen3-Coder-Next-FP8
    --host 0.0.0.0
    --port 8000
    --dtype auto
    --kv-cache-dtype fp8
    --gpu-memory-utilization 0.9
    --max-model-len 131072
```

**Requirements**:
- NVIDIA GPU with CUDA 12.6+
- ~32GB GPU memory

### Using GGUF (llama.cpp)

```bash
./up.sh gguf
```

Configuration in `docker-compose.yml`:
```yaml
qwen3-coder-gguf:
  build:
    context: .
    dockerfile: llama-server-gguf.Dockerfile
  command: >
    --model /models/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf
    --port 8080
    --host 0.0.0.0
    --alias Qwen3-Coder-Next
    -ngl 999
    -fa on
    --no-mmap
    --mlock
    --ctx-size 131072
```

**Requirements**:
- Any NVIDIA GPU with CUDA support
- ~16-24GB combined GPU+CPU memory

## Model Download

### Automatic Download

The `up.sh gguf` script automatically downloads models:

```bash
./up.sh gguf
```

Default model: `Qwen3-Coder-Next-UD-Q4_K_XL.gguf`

### Manual Download

```bash
# Using uvx
uvx --from huggingface_hub hf download \
  unsloth/Qwen3-Coder-Next-GGUF \
  Qwen3-Coder-Next-UD-Q4_K_XL.gguf \
  --local-dir ./models

# Or with huggingface-cli
pip install huggingface_hub
huggingface-cli download unsloth/Qwen3-Coder-Next-GGUF \
  --include "*.gguf" \
  --local-dir ./models
```

### Model Locations

- Default: `./models/`
- Included in `.dockerignore` (not committed to git)

## Choosing a Model

### For Development/Testing

- **GGUF Q4_K_M** - Best balance of quality and memory
- **GGUF Q3_K** - Lower memory footprint

### For Production

- **vLLM FP8** - Best performance on supported GPUs
- **GGUF Q5_K_M** - High quality with reasonable memory

### For Limited Resources

- **GGUF Q2_K** - Minimal VRAM requirement
- **GGUF Q3_K** - Low VRAM with decent quality

## Configuration by Model

### Qwen3-Coder-Next-FP8 (vLLM)

```env
BIG_MODEL=Qwen3-Coder-Next-FP8
SMALL_MODEL=Qwen3-Coder-Next-FP8
VLLM_MAX_CTX=131072
```

### Qwen3.5-122B-A10B (GGUF)

```env
BIG_MODEL=Qwen3.5-122B-A10B-Q4_K_M
SMALL_MODEL=Qwen3.5-122B-A10B-Q4_K_M
VLLM_MAX_CTX=131072
```

## Model Files Structure

```
models/
├── Qwen/
│   └── Qwen3-Coder-Next-FP8/       # vLLM model directory
│       ├── config.json
│       ├── model-00001-of-00003.safetensors
│       └── ...
└── unsloth/
    └── Qwen3-Coder-Next-GGUF/      # GGUF models
        ├── Q4_K_M/
        │   ├── Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf
        │   ├── Qwen3.5-122B-A10B-Q4_K_M-00002-of-00003.gguf
        │   └── Qwen3.5-122B-A10B-Q4_K_M-00003-of-00003.gguf
        └── ...
```

## Performance Recommendations

### vLLM (FP8)

- Enable `--enable-auto-tool-choice` for tool calling
- Set `--gpu-memory-utilization 0.9` for efficient memory use
- Use `--max-model-len 131072` for long context

### GGUF (llama.cpp)

- Use `-fa on` for FlashAttention (faster)
- Enable `--mlock` to prevent swapping
- Set `--parallel` based on GPU count
- Use `--cont-batching` for better throughput

## Troubleshooting

### Out of Memory

- Reduce `VLLM_MAX_CTX`
- Use lower quantization (Q3_K instead of Q4_K_M)
- Reduce `--parallel` workers

### Model Not Found

- Verify model file exists in `./models/`
- Check file permissions
- Ensure container has volume mount

### Poor Performance

- vLLM: Verify GPU memory utilization
- GGUF: Check `--mlock` is enabled
- Both: Monitor with `nvidia-smi`
