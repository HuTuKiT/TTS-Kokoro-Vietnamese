FROM python:3.10-slim

# Avoid Python writing .pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for audio processing and building extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies manually (excluding torch to keep the image extremely lightweight)
RUN pip install --no-cache-dir \
    attrs \
    gradio \
    huggingface_hub \
    loguru \
    numpy \
    packaging \
    soundfile \
    "transformers>=4.48,<5" \
    "vig2p>=0.1.0" \
    fastapi \
    uvicorn \
    pydantic \
    onnx \
    onnxruntime

# Copy local source files (including the pre-converted 'models' directory)
COPY . /app

# Install local package in editable mode without pulling dependencies (avoiding torch)
RUN pip install --no-cache-dir --no-deps -e .

EXPOSE 7888

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7888/v1/health')" || exit 1

# Start uvicorn server
CMD ["kokoro-vietnamese-serve", "--host", "0.0.0.0", "--port", "7888", "--device", "cpu"]
