# spark-gguf.Dockerfile

# --------------------------------------------------------
# STAGE 1: Build the CUDA-enabled ARM64 binaries
# --------------------------------------------------------
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone the latest llama.cpp repository
RUN git clone https://github.com/ggml-org/llama.cpp.git .

# Critical step: Set linker flags so the ARM64 container can 
# successfully compile against the Spark's CUDA stubs
ENV CMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs
RUN cmake -B build \
    -DGGML_CUDA=ON \
    -DLLAMA_CURL=ON \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,--allow-shlib-undefined" \
    && cmake --build build --config Release -j $(nproc)

# --------------------------------------------------------
# STAGE 2: Create the lean runtime image
# --------------------------------------------------------
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y libcurl4 libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the compiled binaries from the builder stage
COPY --from=builder /app/build/bin/llama-server /app/llama-server
COPY --from=builder /app/build/bin/*.so* /app/

# Ensure the container knows where to find the Spark's host drivers
ENV LD_LIBRARY_PATH=/app:/usr/local/cuda/lib64:/usr/local/cuda/compat:$LD_LIBRARY_PATH

ENTRYPOINT ["/app/llama-server"]