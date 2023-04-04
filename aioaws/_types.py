from typing import Protocol


class BaseConfigProtocol(Protocol):
    aws_access_key: str
    aws_secret_key: str
    aws_region: str
    # aws_host and aws_host_scheme are optional and will be inferred if omitted
    # aws_host: str
    # aws_host_schema: str


class S3ConfigProtocol(Protocol):
    aws_access_key: str
    aws_secret_key: str
    aws_region: str
    aws_s3_bucket: str
