import io
import uuid

import boto3
import pytest
from botocore.config import Config
from moto.server import ThreadedMotoServer
from PIL import Image


@pytest.fixture(scope="session")
def moto_server():
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def s3(moto_server, settings):
    bucket = f"test-{uuid.uuid4().hex[:12]}"
    settings.S3_STORAGE = {
        "endpoint_url": moto_server,
        "public_endpoint_url": moto_server,
        "region": "us-east-1",
        "bucket": bucket,
        "access_key_id": "test",
        "secret_access_key": "test",
        "addressing_style": "path",
    }
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(s3={"addressing_style": "path"}),
    )
    client.create_bucket(Bucket=bucket)
    client.bucket = bucket
    yield client
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])
    client.delete_bucket(Bucket=bucket)


def pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def png_bytes(width: int = 20, height: int = 10) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def jpeg_with_exif(orientation: int | None = None) -> bytes:
    image = Image.new("RGB", (20, 10), (30, 30, 200))
    exif = Image.Exif()
    exif[0x010F] = "PhoneCo"  # Make
    if orientation is not None:
        exif[0x0112] = orientation
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()
