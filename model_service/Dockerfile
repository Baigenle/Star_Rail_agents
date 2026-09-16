# Use the DaoCloud proxy for the official PyTorch CUDA runtime. This keeps the
# inference image much smaller than NVIDIA's full NGC development image and is
# reachable when Docker Hub authentication is unreliable in mainland China.
FROM docker.m.daocloud.io/pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /service

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
