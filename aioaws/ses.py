import base64
import mimetypes
import re
from dataclasses import dataclass
from email.encoders import encode_base64
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.utils import formataddr
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import urlencode

import aiofiles
from httpx import AsyncClient

from .core import AwsClient

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol

__all__ = 'SesAttachment', 'SesClient', 'SesConfig', 'Recipient'
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
class Recipient:
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


def as_recipient(r: Union[str, Recipient]) -> Recipient:
    if isinstance(r, Recipient):
        return r
    else:
        return Recipient(r)


class SesClient:
    __slots__ = '_config', '_aws_client'

    def __init__(self, async_client: AsyncClient, config: 'BaseConfigProtocol'):
        self._aws_client = AwsClient(async_client, config, 'ses')
        self._config = config

    async def send_email(
        self,
        e_from: Union[str, Recipient],
        subject: str,
        to: Optional[List[Union[str, Recipient]]] = None,
        text_body: Optional[str] = None,
        html_body: Optional[str] = None,
        *,
        cc: Optional[List[Union[str, Recipient]]] = None,
        bcc: Optional[List[Union[str, Recipient]]] = None,
        attachments: Optional[List[SesAttachment]] = None,
        smtp_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        # TODO explicitly list X-SES-* headers as arguments
        if not any((text_body, html_body)):
            raise TypeError('either "text_body" or "html_body" must be provided when sending emails')

        email_msg = EmailMessage()
        email_msg['Subject'] = subject
        e_from_recipient = as_recipient(e_from)
        email_msg['From'] = e_from_recipient.display()

        to_r: List[Recipient] = []
        cc_r: List[Recipient] = []
        bcc_r: List[Recipient] = []
        if to:
            to_r = [as_recipient(r) for r in to]
            email_msg['To'] = ', '.join(r.display() for r in to_r)
        if cc:
            cc_r = [as_recipient(r) for r in cc]
            email_msg['Cc'] = ', '.join(r.display() for r in cc_r)
        if bcc:
            bcc_r = [as_recipient(r) for r in bcc]
            email_msg['Bcc'] = ', '.join(r.display() for r in bcc_r)

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
        self, e_from: str, email_msg: EmailMessage, *, to: List[Recipient], cc: List[Recipient], bcc: List[Recipient],
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
