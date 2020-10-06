import base64
import hashlib
import hmac
import logging
from binascii import hexlify
from functools import reduce
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from httpx import URL, AsyncClient, Response

from ._utils import get_config_attr, utcnow

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol

__all__ = 'AwsClient', 'RequestError'
logger = logging.getLogger('aioaws.core')

_AWS_AUTH_REQUEST = 'aws4_request'
_CONTENT_TYPE = 'application/x-www-form-urlencoded'
_CANONICAL_REQUEST = """\
{method}
{path}
{query}
{canonical_headers}
{signed_headers}
{payload_hash}"""
_AUTH_ALGORITHM = 'AWS4-HMAC-SHA256'
_CREDENTIAL_SCOPE = '{date_stamp}/{region}/{service}/{auth_request}'
_STRING_TO_SIGN = """\
{algorithm}
{x_amz_date}
{credential_scope}
{canonical_request_hash}"""
_AUTH_HEADER = (
    '{algorithm} Credential={access_key}/{credential_scope},SignedHeaders={signed_headers},Signature={signature}'
)


class AwsClient:
    """
    HTTP client for AWS with authentication
    """

    def __init__(self, client: AsyncClient, config: 'BaseConfigProtocol', service: Literal['s3', 'ses']):
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
                self.host = get_config_attr(config, 'aws_s3_bucket')
            else:
                self.host = f'{bucket}.s3.amazonaws.com'

        self.endpoint = f'https://{self.host}'

    async def get(self, path: str = '', *, params: Optional[Dict[str, Any]] = None) -> Response:
        return await self.request('GET', path=path, params=params)

    async def post(
        self,
        path: str = '',
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> Response:
        return await self.request('POST', path=path, params=params, data=data, content_type=content_type)

    async def request(
        self,
        method: Literal['GET', 'POST'],
        *,
        path: str,
        params: Optional[Dict[str, Any]],
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> Response:
        url = URL(f'https://{self.host}{path}', params=[(k, v) for k, v in sorted((params or {}).items())])
        r = await self.client.request(
            method,
            url,
            data=data,  # type: ignore
            headers=self._auth_headers(method, url, data=data, content_type=content_type),
        )
        if r.status_code != 200:
            raise RequestError(r)
        #     debug(r.status_code, r.url, dict(r.request.headers), r.history, r.content)
        #
        #     from xml.etree import ElementTree
        #     xml_root = ElementTree.fromstring(r.content)
        #     debug(
        #         xml_root.find('StringToSign').text,
        #         xml_root.find('CanonicalRequest').text,
        #     )
        return r

    def _auth_headers(
        self,
        method: Literal['GET', 'POST'],
        url: URL,
        *,
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, str]:
        n = utcnow()
        x_amz_date = n.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = n.strftime('%Y%m%d')
        data = data or b''
        content_type = content_type or _CONTENT_TYPE
        headers = {'content-type': content_type, 'host': self.host, 'x-amz-date': x_amz_date}
        if data is not None:
            headers['content-md5'] = base64.b64encode(hashlib.md5(data).digest()).decode()
        headers = {k: v for k, v in sorted(headers.items())}
        ctx = dict(
            method=method,
            path=url.path,
            query=url.query.decode(),
            access_key=self.aws_access_key,
            algorithm=_AUTH_ALGORITHM,
            x_amz_date=x_amz_date,
            auth_request=_AWS_AUTH_REQUEST,
            date_stamp=date_stamp,
            payload_hash=hashlib.sha256(data).hexdigest(),
            region=self.region,
            service=self.service,
            signed_headers=';'.join(headers.keys()),
        )
        ctx.update(credential_scope=_CREDENTIAL_SCOPE.format(**ctx))
        canonical_headers = ''.join(f'{k}:{v}\n' for k, v in headers.items())

        canonical_request = _CANONICAL_REQUEST.format(canonical_headers=canonical_headers, **ctx).encode()

        s2s = _STRING_TO_SIGN.format(canonical_request_hash=hashlib.sha256(canonical_request).hexdigest(), **ctx)

        key_parts = (
            b'AWS4' + self.aws_secret_key.encode(),
            date_stamp,
            self.region,
            self.service,
            _AWS_AUTH_REQUEST,
            s2s,
        )
        signature: bytes = reduce(_reduce_signature, key_parts)  # type: ignore

        authorization_header = _AUTH_HEADER.format(signature=hexlify(signature).decode(), **ctx)
        headers.update(
            {'authorization': authorization_header, 'x-amz-content-sha256': hashlib.sha256(data).hexdigest()}
        )
        return headers


def _reduce_signature(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


class RequestError(RuntimeError):
    def __init__(self, r: Response):
        error_msg = f'unexpected response from {r.request.method} "{r.request.url}": {r.status_code}'
        super().__init__(error_msg)
        self.response = r
        self.status = r.status_code

    def __str__(self) -> str:
        return f'{self.args[0]}, response:\n{self.response.text}'
