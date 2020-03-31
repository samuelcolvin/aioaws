from typing import Protocol


class BaseConfigProtocol(Protocol):
    aws_access_key: str
    aws_secret_key: str
    aws_region: str


class S3ConfigProtocol(Protocol):
    aws_access_key: str
    aws_secret_key: str
    aws_region: str
    aws_s3_bucket: str
