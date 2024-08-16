import base64
import json
import logging
import mimetypes
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from email.encoders import encode_base64
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.utils import formataddr
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional
from urllib.parse import urlencode

import aiofiles
from httpx import AsyncClient
from pydantic import TypeAdapter

from . import sns
from .core import AwsClient

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol

__all__ = 'SesAttachment', 'SesClient', 'SesConfig', 'SesRecipient', 'SesWebhookInfo'
logger = logging.getLogger('aioaws.ses')
max_total_size = 10 * 1024 * 1024


@dataclass
class SesConfig:
    aws_access_key: str
    aws_secret_key: str
    aws_region: str


@dataclass
class SesAttachment:
    file: Path | bytes
    name: str | None = None
    mime_type: str | None = None
    content_id: str | None = None


@dataclass
class SesRecipient:
    email: str
    first_name: str | None = None
    last_name: str | None = None

    def display(self) -> str:
        if self.first_name and self.last_name:
            name: str | None = f'{self.first_name} {self.last_name}'
        elif self.first_name or self.last_name:
            name = self.first_name or self.last_name
        else:
            name = None
        return formataddr((name, self.email))


class SesClient:
    __slots__ = '_config', '_aws_client'

    def __init__(self, http_client: AsyncClient, config: 'BaseConfigProtocol'):
        self._aws_client = AwsClient(http_client, config, 'ses')
        self._config = config

    async def send_email(
        self,
        e_from: str | SesRecipient,
        subject: str,
        to: list[str | SesRecipient] | None = None,
        text_body: str = '',
        html_body: str | None = None,
        *,
        cc: list[str | SesRecipient] | None = None,
        bcc: list[str | SesRecipient] | None = None,
        attachments: list[SesAttachment] | None = None,
        unsubscribe_link: str | None = None,
        configuration_set: str | None = None,
        message_tags: dict[str, Any] | None = None,
        smtp_headers: dict[str, str] | None = None,
    ) -> str:
        email_msg = EmailMessage()
        email_msg['Subject'] = subject
        e_from_recipient = as_recipient(e_from)
        email_msg['From'] = e_from_recipient.display()

        to_r: list[SesRecipient] = []
        cc_r: list[SesRecipient] = []
        bcc_r: list[SesRecipient] = []
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
        if attachments:
            email_msg.make_mixed()
            for attachment in attachments:
                attachment_msg, size = await prepare_attachment(attachment)
                total_size += size
                if total_size > max_total_size:
                    raise ValueError(f'attachment size {total_size} greater than 10MB')
                email_msg.attach(attachment_msg)

        return await self.send_raw_email(e_from_recipient.email, email_msg, to=to_r, cc=cc_r, bcc=bcc_r)

    async def send_raw_email(
        self,
        e_from: str,
        email_msg: EmailMessage,
        *,
        to: list[SesRecipient],
        cc: list[SesRecipient],
        bcc: list[SesRecipient],
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
        m = re.search(b'<MessageId>(.+?)</MessageId>', r.content)
        if not m:  # pragma: no cover
            raise RuntimeError('failed to find MessageId in response')
        return m.group(1).decode()


def as_recipient(r: str | SesRecipient) -> SesRecipient:
    if isinstance(r, SesRecipient):
        return r
    else:
        return SesRecipient(r)


async def prepare_attachment(a: SesAttachment) -> tuple[MIMEBase, int]:
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

    if a.content_id is None:
        msg.add_header('Content-Disposition', 'attachment', filename=filename)
    else:
        msg.add_header('Content-ID', a.content_id)
        msg.add_header('Content-Disposition', 'inline', filename=filename)
    return msg, len(data)


DateTimeParser = TypeAdapter(datetime)


@dataclass
class SesWebhookInfo:
    message_id: str
    event_type: Literal['send', 'delivery', 'open', 'click', 'bounce', 'complaint']
    timestamp: datetime | None
    unsubscribe: bool
    details: dict[str, Any]
    tags: dict[str, str]
    full_message: dict[str, Any]
    request_data: dict[str, Any]

    @classmethod
    async def build(cls, request_body: str | bytes, http_client: AsyncClient) -> Optional['SesWebhookInfo']:
        payload = await sns.verify_webhook(request_body, http_client)
        if not payload:
            # happens legitimately for subscription confirmation webhooks
            return None

        try:
            message = json.loads(payload.message)
        except ValueError:
            # this can happen legitimately, e.g. when a new configuration set is setup
            logger.warning('invalid JSON in SNS notification', extra={'data': {'request': payload.request_data}})
            return None

        event_type = message['eventType'].lower()

        if event_type not in {'send', 'delivery', 'open', 'click', 'bounce', 'complaint'}:
            logger.warning(
                'unknown aws webhook event %s', event_type, extra={'data': {'request': payload.request_data}}
            )

        message_id = message['mail']['messageId']

        details = message.get(event_type) or {}
        mail = message.get('mail') or {}
        tags = mail.get('tags') or {}
        timestamp = details.get('timestamp') or mail.get('timestamp')

        if event_type == 'bounce':
            unsubscribe = details.get('bounceType') == 'Permanent'
        elif event_type == 'complaint':
            unsubscribe = True
        else:
            unsubscribe = False
        return cls(
            message_id=message_id,
            event_type=event_type,
            timestamp=timestamp and DateTimeParser.validate_strings(timestamp),
            unsubscribe=unsubscribe,
            tags={k: v[0] for k, v in tags.items()},
            details=details,
            full_message=message,
            request_data=payload.request_data,
        )
