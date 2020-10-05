import base64
import json
import logging
import mimetypes
import re
from dataclasses import dataclass
from email.encoders import encode_base64
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.utils import formataddr
from pathlib import Path
from secrets import compare_digest
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Optional, Tuple, Union
from urllib.parse import urlencode

import aiofiles
from httpx import AsyncClient

from .core import AwsClient

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol

__all__ = 'SesAttachment', 'SesClient', 'SesConfig', 'SesRecipient', 'SesWebhookInfo', 'SesWebhookAuthError'
logger = logging.getLogger('aioaws.ses')
max_total_size = 10 * 1024 * 1024


@dataclass
class SesConfig:
    aws_access_key: str
    aws_secret_key: str
    aws_region: str


@dataclass
class SesAttachment:
    file: Union[Path, bytes]
    name: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class SesRecipient:
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    def display(self) -> str:
        if self.first_name and self.last_name:
            name: Optional[str] = f'{self.first_name} {self.last_name}'
        elif self.first_name or self.last_name:
            name = self.first_name or self.last_name
        else:
            name = None
        return formataddr((name, self.email))


class SesClient:
    __slots__ = '_config', '_aws_client'

    def __init__(self, async_client: AsyncClient, config: 'BaseConfigProtocol'):
        self._aws_client = AwsClient(async_client, config, 'ses')
        self._config = config

    async def send_email(
        self,
        e_from: Union[str, SesRecipient],
        subject: str,
        to: Optional[List[Union[str, SesRecipient]]] = None,
        text_body: str = '',
        html_body: Optional[str] = None,
        *,
        cc: Optional[List[Union[str, SesRecipient]]] = None,
        bcc: Optional[List[Union[str, SesRecipient]]] = None,
        attachments: Optional[List[SesAttachment]] = None,
        unsubscribe_link: Optional[str] = None,
        configuration_set: Optional[str] = None,
        message_tags: Optional[Dict[str, Any]] = None,
        smtp_headers: Optional[Dict[str, str]] = None,
    ) -> str:

        email_msg = EmailMessage()
        email_msg['Subject'] = subject
        e_from_recipient = as_recipient(e_from)
        email_msg['From'] = e_from_recipient.display()

        to_r: List[SesRecipient] = []
        cc_r: List[SesRecipient] = []
        bcc_r: List[SesRecipient] = []
        if to:
            to_r = [as_recipient(r) for r in to]
            email_msg['To'] = ', '.join(r.display() for r in to_r)
        if cc:
            cc_r = [as_recipient(r) for r in cc]
            email_msg['Cc'] = ', '.join(r.display() for r in cc_r)
        if bcc:
            bcc_r = [as_recipient(r) for r in bcc]
            email_msg['Bcc'] = ', '.join(r.display() for r in bcc_r)

        if unsubscribe_link:
            email_msg['List-Unsubscribe'] = f'<{unsubscribe_link}>'
        if configuration_set:
            email_msg['X-SES-CONFIGURATION-SET'] = configuration_set
        if message_tags:
            email_msg['X-SES-MESSAGE-TAGS'] = ', '.join(f'{k}={v}' for k, v in message_tags.items())

        if smtp_headers:
            for name, value in smtp_headers.items():
                email_msg[name] = value

        email_msg.set_content(text_body)
        if html_body:
            email_msg.add_alternative(html_body, subtype='html')

        total_size = 0
        for attachment in attachments or []:
            attachment_msg, size = await prepare_attachment(attachment)
            total_size += size
            if total_size > max_total_size:
                raise ValueError(f'attachment size {total_size} greater than 10MB')
            if email_msg.get_content_maintype() == 'text':
                email_msg.make_mixed()
            email_msg.attach(attachment_msg)

        return await self.send_raw_email(e_from_recipient.email, email_msg, to=to_r, cc=cc_r, bcc=bcc_r)

    async def send_raw_email(
        self,
        e_from: str,
        email_msg: EmailMessage,
        *,
        to: List[SesRecipient],
        cc: List[SesRecipient],
        bcc: List[SesRecipient],
    ) -> str:
        if not any((to, cc, bcc)):
            raise TypeError('either "to", "cc", or "bcc" must be provided when sending emails')

        form_data = {
            'Action': 'SendRawEmail',
            'Source': e_from,
            'RawMessage.Data': base64.b64encode(email_msg.as_string().encode()),
        }

        def add_addresses(name: str, addresses: Iterable[str]) -> None:
            form_data.update({f'Destination.{name}.member.{i}': t.encode() for i, t in enumerate(addresses, start=1)})

        if to:
            add_addresses('ToAddresses', (r.email for r in to))
        if cc:
            add_addresses('CcAddresses', (r.email for r in cc))
        if bcc:
            add_addresses('BccAddresses', (r.email for r in bcc))

        data = urlencode(form_data).encode()
        r = await self._aws_client.post('/', data=data)
        return re.search('<MessageId>(.+?)</MessageId>', r.text).group(1)  # type: ignore


def as_recipient(r: Union[str, SesRecipient]) -> SesRecipient:
    if isinstance(r, SesRecipient):
        return r
    else:
        return SesRecipient(r)


async def prepare_attachment(a: SesAttachment) -> Tuple[MIMEBase, int]:
    filename = a.name
    if filename is None and isinstance(a.file, Path):
        filename = a.file.name
    filename = filename or 'attachment'

    mime_type, encoding = mimetypes.guess_type(filename)
    if mime_type is None or encoding is not None:
        mime_type = 'application/octet-stream'
    maintype, subtype = mime_type.split('/', 1)

    if isinstance(a.file, Path):
        async with aiofiles.open(a.file, mode='rb') as fp:
            data = await fp.read()
    else:
        data = a.file

    msg = MIMEBase(maintype, subtype)
    msg.set_payload(data)
    encode_base64(msg)

    msg.add_header('Content-Disposition', 'attachment', filename=filename)
    return msg, len(data)


class SesWebhookAuthError(ValueError):
    def __init__(self, message: str, headers: Dict[str, str] = None):
        super().__init__(message)
        self.message = message
        self.headers = headers or {}


@dataclass
class SesWebhookInfo:
    message_id: str
    event_type: Literal['send', 'open', 'click', 'bounce', 'complaint']
    unsubscribe: bool
    extra: Dict[str, Any]
    raw: Dict[str, Any]

    @classmethod
    async def build(
        cls, auth_header: Optional[str], request_text: str, aws_ses_webhook_auth: bytes, async_client: AsyncClient
    ) -> Optional['SesWebhookInfo']:
        expected_auth_header = f'Basic {base64.b64encode(aws_ses_webhook_auth).decode()}'
        if not compare_digest(expected_auth_header, auth_header or ''):
            raise SesWebhookAuthError('Invalid basic auth', headers={'WWW-Authenticate': 'Basic'})

        request_data = json.loads(request_text)
        sns_type = request_data['Type']
        if sns_type == 'SubscriptionConfirmation':
            logger.info('confirming aws Subscription')
            sub_url = request_data['SubscribeURL']
            r = await async_client.get(sub_url)
            r.raise_for_status()
            return None

        assert sns_type == 'Notification', sns_type
        raw_message = request_data['Message']
        message = json.loads(raw_message)

        event_type = message['eventType'].lower()
        message_id = message['mail']['messageId']
        logger.info('%s for message %s', event_type, message_id)

        data = message.get(event_type) or {}
        extra = {
            'delivery_time': data.get('processingTimeMillis'),
            'ip_address': data.get('ipAddress'),
            'user_agent': data.get('userAgent'),
            'link': data.get('link'),
            'bounce_type': data.get('bounceType'),
            'bounce_subtype': data.get('bounceSubType'),
            'reporting_mta': data.get('reportingMTA'),
            'feedback_id': data.get('feedbackId'),
            'complaint_feedback_type': data.get('complaintFeedbackType'),
        }
        extra = {k: v for k, v in extra.items() if v is not None}
        unsubscribe = False
        if event_type == 'bounce':
            unsubscribe = data.get('bounceType') == 'Permanent'
        elif event_type == 'complaint':
            unsubscribe = True

        if event_type not in {'send', 'open', 'click', 'bounce', 'complaint'}:
            logger.warning('unknown aws webhook event %s', event_type, extra={'data': {'message': message}})

        return cls(message_id=message_id, event_type=event_type, unsubscribe=unsubscribe, extra=extra, raw=message)
