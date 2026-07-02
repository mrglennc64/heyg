FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip ffmpeg librubberband2 libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/local/bin/python

WORKDIR /app
COPY services/voice/requirements.txt .
RUN pip install --no-cache-dir torch==2.4.* --index-url https://download.pytorch.org/whl/cu121 \
    && pip install --no-cache-dir -r requirements.txt

COPY shared/ /opt/shared/
RUN pip install --no-cache-dir -e /opt/shared

COPY services/voice/worker ./worker

# XTTS v2 license: Coqui Public Model License (non-commercial clause) —
# review before commercial deployment, or swap in an Apache-2.0 TTS.
ENV COQUI_TOS_AGREED=1
