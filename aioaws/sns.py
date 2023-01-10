import base64
import json
import logging
import re
from typing import Any, Dict, Literal, Optional, Tuple, Union

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from httpx import AsyncClient
from pydantic import BaseModel, Field, HttpUrl, ValidationError, validator

__all__ = 'SnsWebhookError', 'SnsPayload', 'verify_webhook'
logger = logging.getLogger('aioaws.sns')


class SnsWebhookError(ValueError):
    def __init__(self, message: str, details: Any = None, headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers or {}


class SnsPayload(BaseModel):
    type: Literal['Notification', 'SubscriptionConfirmation', 'UnsubscribeConfirmation'] = Field(..., alias='Type')
    signing_cert_url: HttpUrl = Field(..., alias='SigningCertURL')
    signature: bytes = Field(..., alias='Signature')
    subscribe_url: HttpUrl = Field(None, alias='SubscribeURL')
    message: str = Field(str, alias='Message')
    request_data: Dict[str, Any]

    @validator('signature', pre=True)
    def base64_signature(cls, sig: str) -> bytes:
        return base64.b64decode(sig)


async def verify_webhook(request_body: Union[str, bytes], http_client: AsyncClient) -> Optional[SnsPayload]:
    try:
        request_data = json.loads(request_body)
    except ValueError as e:
        raise SnsWebhookError('invalid JSON') from e

    try:
        payload = SnsPayload(**request_data, request_data=request_data)
    except ValidationError as e:
        logger.warning('invalid SNS webhook payload %s', e)
        raise SnsWebhookError('invalid payload', details=e.errors()) from e

    await verify_signature(payload, http_client)

    if payload.type == 'SubscriptionConfirmation':
        logger.info('confirming aws Subscription')
        await get_resources(payload.subscribe_url, http_client)
        return None
    else:
        return payload


async def verify_signature(payload: SnsPayload, http_client: AsyncClient) -> None:
    url = payload.signing_cert_url
    if url.host is None or not re.fullmatch(r'sns\.[a-z0-9\-]+\.amazonaws\.com', url.host):
        raise SnsWebhookError(f'invalid SigningCertURL "{url}"')

    certs_content = await get_resources(url, http_client)

    cert = x509.load_pem_x509_certificate(certs_content)

    message = get_message(payload)
    try:
        cert.public_key().verify(payload.signature, message, padding.PKCS1v15(), hashes.SHA1())  # type: ignore
    except InvalidSignature as e:
        raise SnsWebhookError('invalid signature') from e


def get_message(payload: SnsPayload) -> bytes:
    keys: Tuple[str, ...]
    if payload.type == 'Notification':
        keys = 'Message', 'MessageId', 'Subject', 'Timestamp', 'TopicArn', 'Type'
    else:
        keys = 'Message', 'MessageId', 'SubscribeURL', 'Timestamp', 'Token', 'TopicArn', 'Type'

    parts = []
    for key in keys:
        if value := payload.request_data.get(key):
            parts += [key, value]
    return ''.join(f'{p}\n' for p in parts).encode()


async def get_resources(url: HttpUrl, http_client: AsyncClient) -> bytes:
    r = await http_client.get(str(url))

    if r.status_code != 200:
        logger.warning(
            'unexpected response from %s "%s", %d',
            r.request.method,
            r.request.url,
            r.status_code,
            extra={'data': {'response': r.text}},
        )
        raise SnsWebhookError(f'unexpected response from "{r.request.url}", {r.status_code}')
    return r.content
