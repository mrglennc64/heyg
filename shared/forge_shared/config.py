from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    forge_api_key: str = "dev-key"
    redis_url: str = "redis://redis:6379/0"

    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "forge-artifacts"
    s3_access_key: str = "forge"
    s3_secret_key: str = "forge"

    default_resolution: str = "1920x1080"
    default_fps: int = 25
    max_script_chars: int = 20_000

    watermark_enabled: bool = True
    watermark_key: str = "dev-watermark"

    scratch_dir: str = "/scratch"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def settings() -> Settings:
    return Settings()
