import base64
import hashlib
import hmac
import logging
from binascii import hexlify
from datetime import datetime
from functools import reduce
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Literal, Optional, Tuple
from urllib.parse import quote as url_quote

import httpx

from ._utils import get_config_attr, utcnow

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol

__all__ = 'AwsClient', 'RequestError'
logger = logging.getLogger('aioaws.core')

_AWS_AUTH_REQUEST = 'aws4_request'
_CONTENT_TYPE = 'application/x-www-form-urlencoded'
_AUTH_ALGORITHM = 'AWS4-HMAC-SHA256'


def _aws4_date_stamp(dt: datetime) -> str:
    return dt.strftime('%Y%m%d')


def _aws4_x_amz_date(dt: datetime) -> str:
    return dt.strftime('%Y%m%dT%H%M%SZ')


def _aws4_reduce_signature(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


class _AWSv4Auth:
    def __init__(
        self,
        aws_secret_key: str,
        aws_access_key_id: str,
        region: str,
        service: str,
    ) -> None:
        self.aws_secret_key = aws_secret_key
        self.aws_access_key_id = aws_access_key_id
        self.region = region
        self.service = service

    def auth_headers(
        self,
        method: Literal['GET', 'POST'],
        url: httpx.URL,
        *,
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, str]:
        now = utcnow()
        data = data or b''
        content_type = content_type or _CONTENT_TYPE

        # WARNING! order is important here, headers need to be in alphabetical order
        headers = {
            'content-md5': base64.b64encode(hashlib.md5(data).digest()).decode(),
            'content-type': content_type,
            'host': url.host,
            'x-amz-date': _aws4_x_amz_date(now),
        }

        payload_sha256_hash = hashlib.sha256(data).hexdigest()
        signed_headers, signature = self.aws4_signature(now, method, url, headers, payload_sha256_hash)
        credential = self.aws4_credential(now)
        authorization_header = (
            f'{_AUTH_ALGORITHM} Credential={credential},SignedHeaders={signed_headers},Signature={signature}'
        )
        headers.update({'authorization': authorization_header, 'x-amz-content-sha256': payload_sha256_hash})
        return headers

    def aws4_signature(
        self, dt: datetime, method: Literal['GET', 'POST'], url: httpx.URL, headers: Dict[str, str], payload_hash: str
    ) -> Tuple[str, str]:
        header_keys = sorted(headers)
        signed_headers = ';'.join(header_keys)
        canonical_request_parts = (
            method,
            url_quote(url.path),
            url.query.decode(),
            ''.join(f'{k}:{headers[k]}\n' for k in header_keys),
            signed_headers,
            payload_hash,
        )
        canonical_request = '\n'.join(canonical_request_parts)
        string_to_sign_parts = (
            _AUTH_ALGORITHM,
            _aws4_x_amz_date(dt),
            self._aws4_scope(dt),
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        )
        string_to_sign = '\n'.join(string_to_sign_parts)
        return signed_headers, self.aws4_sign_string(string_to_sign, dt)

    def aws4_sign_string(self, string_to_sign: str, dt: datetime) -> str:
        key_parts = (
            b'AWS4' + self.aws_secret_key.encode(),
            _aws4_date_stamp(dt),
            self.region,
            self.service,
            _AWS_AUTH_REQUEST,
            string_to_sign,
        )
        signature_bytes: bytes = reduce(_aws4_reduce_signature, key_parts)  # type: ignore
        return hexlify(signature_bytes).decode()

    def _aws4_scope(self, dt: datetime) -> str:
        return f'{_aws4_date_stamp(dt)}/{self.region}/{self.service}/{_AWS_AUTH_REQUEST}'

    def aws4_credential(self, dt: datetime) -> str:
        return f'{self.aws_access_key_id}/{self._aws4_scope(dt)}'



class AwsClient:
    """
    HTTP client for AWS with authentication
    """

    def __init__(self, client: httpx.AsyncClient, config: 'BaseConfigProtocol', service: Literal['s3', 'ses']):
        self.client = client
        self.aws_access_key = get_config_attr(config, 'aws_access_key')
        self.aws_secret_key = get_config_attr(config, 'aws_secret_key')
        self.service = service
        self.region = get_config_attr(config, 'aws_region')
        if self.service == 'ses':
            self.host = f'email.{self.region}.amazonaws.com'
        else:
            assert self.service == 's3', self.service
            bucket = get_config_attr(config, 'aws_s3_bucket')
            if '.' in bucket:
                # assumes the bucket is a domain and is already as a CNAME record for S3
                self.host = bucket
            else:
                # see https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-bucket-intro.html
                self.host = f'{bucket}.s3.{self.region}.amazonaws.com'

        self.endpoint = f'https://{self.host}'
        self._auth = _AWSv4Auth(
            aws_secret_key=self.aws_secret_key,
            aws_access_key_id=self.aws_access_key,
            region=self.region,
            service=self.service,
        )

    async def get(self, path: str = '', *, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        return await self.request('GET', path=path, params=params)

    async def raw_post(
        self,
        url: str,
        *,
        expected_status: int,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, bytes]] = None,
    ) -> httpx.Response:
        r = await self.client.post(url, params=params, data=data, files=files)
        if r.status_code == expected_status:
            return r
        else:
            # from ._utils import pretty_response
            # pretty_response(r)
            raise RequestError(r)

    async def post(
        self,
        path: str = '',
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> httpx.Response:
        return await self.request('POST', path=path, params=params, data=data, content_type=content_type)

    async def request(
        self,
        method: Literal['GET', 'POST'],
        *,
        path: str,
        params: Optional[Dict[str, Any]],
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> httpx.Response:
        url = httpx.URL(f'{self.endpoint}{path}', params=[(k, v) for k, v in sorted((params or {}).items())])
        r = await self.client.request(
            method,
            url,
            content=data,
            headers=self._auth.auth_headers(method, url, data=data, content_type=content_type),
        )
        if r.status_code != 200:
            # from ._utils import pretty_response
            # pretty_response(r)
            raise RequestError(r)
        return r

    def add_signed_download_params(self, method: Literal['GET', 'POST'], url: httpx.URL, expires: int = 86400) -> httpx.URL:
        assert expires >= 1, f'expires must be greater than or equal to 1, not {expires}'
        assert expires <= 604800, f'expires must be less than or equal to 604800, not {expires}'
        now = utcnow()
        url = url.copy_merge_params(
            {
                'X-Amz-Algorithm': _AUTH_ALGORITHM,
                'X-Amz-Credential': self._auth.aws4_credential(now),
                'X-Amz-Date': _aws4_x_amz_date(now),
                'X-Amz-Expires': str(expires),
                'X-Amz-SignedHeaders': 'host',
            }
        )
        _, signature = self._auth.aws4_signature(now, method, url, {'host': self.host}, 'UNSIGNED-PAYLOAD')
        return url.copy_add_param('X-Amz-Signature', signature)

    def upload_extra_conditions(self, dt: datetime) -> List[Dict[str, str]]:
        return [
            {'x-amz-credential': self._auth.aws4_credential(dt)},
            {'x-amz-algorithm': _AUTH_ALGORITHM},
            {'x-amz-date': _aws4_x_amz_date(dt)},
        ]

    def signed_upload_fields(self, dt: datetime, string_to_sign: str) -> Dict[str, str]:
        return {
            'X-Amz-Algorithm': _AUTH_ALGORITHM,
            'X-Amz-Credential': self._auth.aws4_credential(dt),
            'X-Amz-Date': _aws4_x_amz_date(dt),
            'X-Amz-Signature': self._auth.aws4_sign_string(string_to_sign, dt),
        }


class RequestError(RuntimeError):
    def __init__(self, r: httpx.Response):
        error_msg = f'unexpected response from {r.request.method} "{r.request.url}": {r.status_code}'
        super().__init__(error_msg)
        self.response = r
        self.status = r.status_code

    def __str__(self) -> str:
        return f'{self.args[0]}, response:\n{self.response.text}'


class AWSV4AuthFlow(httpx.Auth):
    def __init__(
        self,
        aws_secret_key: str,
        aws_access_key_id: str,
        region: str,
        service: str,
    ) -> None:
        self._authorizer = _AWSv4Auth(
            aws_secret_key=aws_secret_key,
            aws_access_key_id=aws_access_key_id,
            region=region,
            service=service,
        )

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        auth_headers = self._authorizer.auth_headers(
            method=request.method.upper(),  # type: ignore
            url=request.url,
            data=request.content,
            content_type=request.headers.get("Content-Type")
        )
        request.headers.update(auth_headers)
        yield request
