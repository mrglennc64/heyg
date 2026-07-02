# jrottenberg/ffmpeg ships NVENC-enabled ffmpeg on the nvidia runtime
FROM jrottenberg/ffmpeg:7.0-nvidia AS ffmpeg
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
COPY --from=ffmpeg /usr/local /usr/local

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/local/bin/python

WORKDIR /app
COPY services/compositor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /opt/shared/
RUN pip install --no-cache-dir -e /opt/shared

COPY services/compositor/worker ./worker
