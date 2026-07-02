FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip ffmpeg libgl1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/local/bin/python

WORKDIR /app
COPY services/avatar/requirements.txt .
RUN pip install --no-cache-dir torch==2.4.* torchvision --index-url https://download.pytorch.org/whl/cu121 \
    && pip install --no-cache-dir -r requirements.txt

COPY shared/ /opt/shared/
RUN pip install --no-cache-dir -e /opt/shared

# SadTalker / LivePortrait are vendored under /models (bind mount) with their
# own weights — see infra/models/download_models.sh
COPY services/avatar/worker ./worker
