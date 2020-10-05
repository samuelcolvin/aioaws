import pytest
from foxglove.test_server import DummyServer
from httpx import AsyncClient

from aioaws.ses import Recipient, SesAttachment, SesClient, SesConfig

pytestmark = pytest.mark.asyncio


async def test_send(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    message_id = await ses.send_email(
        'testing@sender.com',
        'test email',
        ['testing@recipient.com'],
        'this is a test email',
        html_body='This is a <b>test</b> email.',
    )
    assert message_id == '123-message-id'

    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['body']['Action'] == 'SendRawEmail'
    assert eml['body']['Source'] == 'testing@sender.com'
    assert eml['body']['Destination.ToAddresses.member.1'] == 'testing@recipient.com'
    assert eml['email'] == {
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
        ['testing@recipient.com'],
        'this is a test email',
        attachments=[SesAttachment(file=b'some binary data', name='testing.txt', mime_type='text/plain')],
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['email'] == {
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


async def test_send_names(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    await ses.send_email(
        'testing@sender.com',
        'test email',
        [Recipient('testing@example.com', 'John', 'Doe')],
        'this is a test email',
        cc=[
            Recipient('cc1@example.com'),
            Recipient('cc2@example.com', 'CC2'),
            Recipient('cc3@example.com', None, 'CC3'),
            Recipient('cc4@example.com', 'Anna, Bob', 'CC4'),
        ],
        bcc=['bcc@exmaple.com'],
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['email'] == {
        'Subject': 'test email',
        'From': 'testing@sender.com',
        'Content-Transfer-Encoding': '7bit',
        'MIME-Version': '1.0',
        'To': 'John Doe <testing@example.com>',
        'Cc': 'cc1@example.com, CC2 <cc2@example.com>, CC3 <cc3@example.com>,\n "Anna, Bob CC4" <cc4@example.com>',
        'Bcc': 'bcc@exmaple.com',
        'payload': [{'Content-Type': 'text/plain', 'payload': 'this is a test email\n'}],
    }
