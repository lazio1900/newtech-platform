# MinerU 내장 HTTP API 서버 컨테이너.
# /file_parse 엔드포인트로 PDF 를 markdown 으로 변환. CPU 파이프라인 모드.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# opencv / PaddleOCR 런타임 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip uv && \
    uv pip install --system "mineru[all]"

# 모델 캐시 — compose 의 named volume 이 마운트됨. 첫 호출에서 다운로드 (~수 GB).
ENV HF_HOME=/models/hf \
    TORCH_HOME=/models/torch \
    MINERU_MODEL_SOURCE=huggingface
RUN mkdir -p /models/hf /models/torch

EXPOSE 8000
CMD ["mineru-api", "--host", "0.0.0.0", "--port", "8000"]
