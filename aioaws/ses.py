import base64
import mimetypes
import re
from dataclasses import dataclass
from email.encoders import encode_base64
from email.message import EmailMessage
from email.mime.base import MIMEBase
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlencode

import aiofiles
from httpx import AsyncClient

from .core import AwsClient

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol

__all__ = 'SesAttachment', 'SesClient', 'SesConfig'
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


class SesClient:
    __slots__ = '_config', '_aws_client'

    def __init__(self, async_client: AsyncClient, config: 'BaseConfigProtocol'):
        self._aws_client = AwsClient(async_client, config, 'ses')
        self._config = config

    async def send_email(
        self,
        e_from: str,
        subject: str,
        to: Optional[Set[str]] = None,
        text_body: Optional[str] = None,
        html_body: Optional[str] = None,
        *,
        cc: Optional[Set[str]] = None,
        bcc: Optional[Set[str]] = None,
        attachments: Optional[List[SesAttachment]] = None,
        smtp_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        # TODO explicitly list X-SES-* headers as arguments
        if not any((text_body, html_body)):
            raise TypeError('either "text_body" or "html_body" must be provided when sending emails')

        email_msg = EmailMessage()
        email_msg['Subject'] = subject
        email_msg['From'] = e_from

        email_msg.set_content(text_body)
        if html_body:
            email_msg.add_alternative(html_body, subtype='html')
        # else:
        #     email_msg.make_alternative()

        total_size = 0
        for attachment in attachments or []:
            attachment_msg, size = await prepare_attachment(attachment)
            total_size += size
            if total_size > max_total_size:
                raise ValueError(f'attachment size {total_size} greater than 10MB')
            if email_msg.get_content_maintype() == 'text':
                email_msg.make_mixed()
            email_msg.attach(attachment_msg)

        if to:
            email_msg['To'] = ','.join(to)
        if cc:
            email_msg['Cc'] = ','.join(cc)
        if bcc:
            email_msg['Bcc'] = ','.join(bcc)

        if smtp_headers:
            for name, value in smtp_headers.items():
                email_msg[name] = value

        return await self.send_raw_email(e_from, email_msg, to=to, cc=cc, bcc=bcc)

    async def send_raw_email(
        self,
        e_from: str,
        email_msg: EmailMessage,
        *,
        to: Optional[Set[str]] = None,
        cc: Optional[Set[str]] = None,
        bcc: Optional[Set[str]] = None,
    ) -> str:
        if not any((to, cc, bcc)):
            raise TypeError('either "to", "cc", or "bcc" must be provided when sending emails')

        form_data = {
            'Action': 'SendRawEmail',
            'Source': e_from,
            'RawMessage.Data': base64.b64encode(email_msg.as_string().encode()),
        }

        def add_addresses(name: str, addresses: Set[str]) -> None:
            form_data.update({f'Destination.{name}.member.{i}': t.encode() for i, t in enumerate(addresses, start=1)})

        if to:
            add_addresses('ToAddresses', to)
        if cc:
            add_addresses('CcAddresses', cc)
        if bcc:
            add_addresses('BccAddresses', bcc)

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
