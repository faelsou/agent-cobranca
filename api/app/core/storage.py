from functools import lru_cache
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

LOCAL_DIR = Path(".data/comprovantes")


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.minio_root_password,
        config=Config(
            signature_version="s3v4",
            connect_timeout=1,
            read_timeout=2,
            retries={"max_attempts": 1},
        ),
        region_name="us-east-1",
    )


def _local_path(key: str) -> Path:
    path = LOCAL_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def put_object(key: str, data: bytes, content_type: str) -> str:
    try:
        _client().put_object(
            Bucket=get_settings().s3_bucket, Key=key, Body=data, ContentType=content_type
        )
        return key
    except (BotoCoreError, ClientError, OSError):
        if get_settings().env == "prod":
            raise
        _local_path(key).write_bytes(data)
        return key


def get_object(key: str) -> bytes:
    try:
        response = _client().get_object(Bucket=get_settings().s3_bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError, OSError):
        path = _local_path(key)
        if path.exists():
            return path.read_bytes()
        raise
