# ReviewPulse web app, CPU image.
#   docker build -t reviewpulse .                          vector plans (PDF, DXF, SVG)
#   docker build -t reviewpulse --build-arg WITH_RASTER=1 .  + scans (torch CPU, PaddleOCR)
# The drafting model runs in its own container (Ollama); see docker-compose.yml.
FROM python:3.11.9-slim-bookworm

ARG WITH_RASTER=0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    REVIEWPULSE_LLM=ollama OLLAMA_HOST=http://ollama:11434

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY docs ./docs
# trained models (data/models/*) are optional: present ones are copied, absent ones disable their path
COPY data ./data
RUN pip install -e ".[app]" lightgbm \
    && if [ "$WITH_RASTER" = "1" ]; then \
         pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
         && pip install segmentation-models-pytorch paddlepaddle==3.2.0 paddleocr ; \
       fi

RUN useradd --create-home --uid 1000 rp && mkdir -p /data && chown rp /data
USER rp
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["rp", "serve", "--host", "0.0.0.0", "--port", "8000", "--data", "/data"]
