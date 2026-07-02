"""MinIO/S3 artifact store.

Every pipeline stage reads its inputs from and writes its outputs to object
storage keyed by job/scene, so workers stay stateless and horizontally
scalable. Large frame sequences use the shared /scratch volume instead and
pass paths — only stage *boundaries* (wav, mp4) go through S3.
"""
from __future__ import annotations

import io
from pathlib import Path

import boto3
from botocore.client import Config as BotoConfig

from .config import settings


def _client():
    s = settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        config=BotoConfig(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    c, bucket = _client(), settings().s3_bucket
    existing = {b["Name"] for b in c.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        c.create_bucket(Bucket=bucket)


def upload(local_path: str | Path, key: str) -> str:
    _client().upload_file(str(local_path), settings().s3_bucket, key)
    return key


def upload_bytes(data: bytes, key: str) -> str:
    _client().upload_fileobj(io.BytesIO(data), settings().s3_bucket, key)
    return key


def download(key: str, local_path: str | Path) -> Path:
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _client().download_file(settings().s3_bucket, key, str(local_path))
    return local_path


def presigned_url(key: str, expires: int = 24 * 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings().s3_bucket, "Key": key},
        ExpiresIn=expires,
    )
