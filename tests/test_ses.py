import base64
from email import message_from_bytes

import pytest
from foxglove.test_server import DummyServer
from httpx import AsyncClient

from aioaws.ses import SesAttachment, SesClient, SesConfig

pytestmark = pytest.mark.asyncio


def email_dict(raw: bytes):
    msg = message_from_bytes(base64.b64decode(raw))
    d = dict(msg)
    d.pop('Content-Type', None)
    d['payload'] = []
    for part in msg.walk():
        if payload := part.get_payload(decode=True):
            part_info = {'Content-Type': part.get_content_type(), 'payload': payload.decode().replace('\r\n', '\n')}
            if cd := part['Content-Disposition']:
                part_info['Content-Disposition'] = cd
            d['payload'].append(part_info)
    return d


async def test_send_email(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    message_id = await ses.send_email(
        'testing@sender.com',
        'test email',
        {'testing@recipient.com'},
        'this is a test email',
        html_body='This is a <b>test</b> email.',
    )
    assert message_id == '123-message-id'

    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['Action'] == 'SendRawEmail'
    assert eml['Source'] == 'testing@sender.com'
    assert eml['Destination.ToAddresses.member.1'] == 'testing@recipient.com'

    msg = email_dict(eml['RawMessage.Data'])
    assert msg == {
        'Subject': 'test email',
        'From': 'testing@sender.com',
        'MIME-Version': '1.0',
        'To': 'testing@recipient.com',
        'payload': [
            {'Content-Type': 'text/plain', 'payload': 'this is a test email\n'},
            {'Content-Type': 'text/html', 'payload': 'This is a <b>test</b> email.\n'},
        ],
    }


async def test_send_email_attachment(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    await ses.send_email(
        'testing@sender.com',
        'test with attachment',
        {'testing@recipient.com'},
        'this is a test email',
        attachments=[SesAttachment(file=b'some binary data', name='testing.txt', mime_type='text/plain')],
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    msg = email_dict(eml['RawMessage.Data'])
    assert msg == {
        'Subject': 'test with attachment',
        'From': 'testing@sender.com',
        'MIME-Version': '1.0',
        'To': 'testing@recipient.com',
        'payload': [
            {'Content-Type': 'text/plain', 'payload': 'this is a test email\n'},
            {
                'Content-Type': 'text/plain',
                'payload': 'some binary data',
                'Content-Disposition': 'attachment; filename="testing.txt"',
            },
        ],
    }
