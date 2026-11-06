"""S3-compatible object storage adapter.

Settings are read at call time from ``settings.S3_STORAGE``. Clients are cached on the tuple of
the values they depend on, so a settings override yields a fresh client. boto3 is imported
lazily. Every botocore failure becomes ``StorageUnavailable``, except a missing object on
``head_size`` and ``copy`` (reported as ``None`` / ``False``).
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from django.conf import settings

_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}


class StorageUnavailable(Exception):
    """Storage could not be reached or refused the request."""


class StorageNotConfigured(StorageUnavailable):
    """Storage settings are incomplete; raised before any network call."""


def _cfg() -> dict[str, str]:
    return settings.S3_STORAGE


def is_configured() -> bool:
    cfg = _cfg()
    names = ("endpoint_url", "bucket", "region", "access_key_id", "secret_access_key")
    return all(cfg.get(name) for name in names)


def _require() -> dict[str, str]:
    if not is_configured():
        raise StorageNotConfigured("Object storage is not configured.")
    return _cfg()


@lru_cache(maxsize=8)
def _build_client(
    endpoint_url: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
    addressing_style: str,
) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": addressing_style or "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 2},
        ),
    )


def _client(*, public: bool = False) -> Any:
    cfg = _require()
    endpoint = (
        (cfg.get("public_endpoint_url") or cfg.get("endpoint_url") or "")
        if public
        else cfg.get("endpoint_url", "")
    )
    return _build_client(
        endpoint,
        cfg["region"],
        cfg["access_key_id"],
        cfg["secret_access_key"],
        cfg.get("addressing_style", "path"),
    )


def _bucket() -> str:
    return _require()["bucket"]


def _is_missing(exc: Exception) -> bool:
    from botocore.exceptions import ClientError

    if not isinstance(exc, ClientError):
        return False
    return str(exc.response.get("Error", {}).get("Code", "")) in _MISSING_CODES


def _unavailable(exc: Exception) -> StorageUnavailable:
    # The message carries only the exception type. The chained botocore error embeds the object
    # URL, so keys must stay opaque UUIDs (pending/<uuid>, files/<purpose>/<uuid>), not file names.
    return StorageUnavailable(f"Object storage request failed ({type(exc).__name__}).")


def presigned_put(*, key: str, content_type: str, size: int, expires: int = 600) -> str:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client(public=True)
    try:
        return str(
            client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": _bucket(),
                    "Key": key,
                    "ContentType": content_type,
                    "ContentLength": size,
                },
                ExpiresIn=expires,
                HttpMethod="PUT",
            )
        )
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc


def presigned_get(*, key: str, content_type: str, disposition: str, expires: int = 300) -> str:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client(public=True)
    try:
        return str(
            client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": _bucket(),
                    "Key": key,
                    "ResponseContentType": content_type,
                    "ResponseContentDisposition": disposition,
                },
                ExpiresIn=expires,
            )
        )
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc


def head_size(key: str) -> int | None:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    try:
        return int(client.head_object(Bucket=_bucket(), Key=key)["ContentLength"])
    except (BotoCoreError, ClientError) as exc:
        if _is_missing(exc):
            return None
        raise _unavailable(exc) from exc


def read_range(key: str, length: int) -> bytes:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    try:
        response = client.get_object(Bucket=_bucket(), Key=key, Range=f"bytes=0-{length - 1}")
        return bytes(response["Body"].read())
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc


def read_all(key: str) -> bytes:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    try:
        response = client.get_object(Bucket=_bucket(), Key=key)
        return bytes(response["Body"].read())
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc


def iter_chunks(key: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    try:
        response = client.get_object(Bucket=_bucket(), Key=key)
        body = response["Body"]
        try:
            yield from body.iter_chunks(chunk_size)
        finally:
            body.close()
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc


def copy(*, source: str, dest: str, content_type: str) -> bool:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    bucket = _bucket()
    try:
        client.copy_object(
            Bucket=bucket,
            Key=dest,
            CopySource={"Bucket": bucket, "Key": source},
            ContentType=content_type,
            MetadataDirective="REPLACE",
        )
    except (BotoCoreError, ClientError) as exc:
        if _is_missing(exc):
            return False
        raise _unavailable(exc) from exc
    return True


def put(*, key: str, body: bytes, content_type: str) -> None:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    try:
        client.put_object(Bucket=_bucket(), Key=key, Body=body, ContentType=content_type)
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc


def delete(key: str) -> None:
    from botocore.exceptions import BotoCoreError, ClientError

    client = _client()
    try:
        client.delete_object(Bucket=_bucket(), Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise _unavailable(exc) from exc
