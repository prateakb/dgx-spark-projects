# 1. Builder Stage
FROM nvidia/cuda:13.0.2-devel-ubuntu24.04 AS builder

RUN apt-get update && apt-get install -y \
    git build-essential cmake libcurl4-openssl-dev

WORKDIR /app
RUN git clone https://github.com/ggml-org/llama.cpp.git .

# THE LINKER FIX: Satisfy the 'libcuda.so.1' requirement during build using stubs
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1

# Build with Blackwell-specific flags
# -DLLAMA_BUILD_EXAMPLES=OFF skips broken example files to focus on the server
RUN cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=121 \
    -DGGML_NATIVE=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DCMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,--allow-shlib-undefined" \
    -DGGML_CUDA_F16=ON \
    -DGGML_FAST_MATH=ON && \
    cmake --build build --config Release -j$(nproc)

# 2. Final Runtime Stage
FROM nvidia/cuda:13.0.2-runtime-ubuntu24.04
WORKDIR /app

# Install OpenMP (required for CPU coordination)
RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*

# Copy the shared libraries and the server binary
COPY --from=builder /app/build/bin/lib*.so* /usr/local/lib/
COPY --from=builder /app/build/bin/llama-server /app/llama-server

# Update library cache so the system 'sees' the new .so files
RUN ldconfig

# Blackwell/Spark runtime pathing
ENV LD_LIBRARY_PATH="/usr/local/lib:/usr/local/cuda/lib64/compat:/usr/local/cuda/lib64:$LD_LIBRARY_PATH"

ENTRYPOINT ["/app/llama-server"]