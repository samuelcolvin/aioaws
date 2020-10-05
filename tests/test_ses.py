import base64
import json
import os

import pytest
from foxglove.test_server import DummyServer
from httpx import AsyncClient
from pytest_toolbox.comparison import RegexStr

from aioaws.ses import Recipient, SesAttachment, SesClient, SesConfig, SesWebhookAuthError, SesWebhookInfo

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
    assert eml['body'] == {
        'Action': 'SendRawEmail',
        'Source': 'testing@sender.com',
        'RawMessage.Data': RegexStr('.+'),
        'Destination.ToAddresses.member.1': 'testing@recipient.com',
    }
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
    assert eml['body'] == {
        'Action': 'SendRawEmail',
        'Source': 'testing@sender.com',
        'RawMessage.Data': RegexStr('.+'),
        'Destination.ToAddresses.member.1': 'testing@example.com',
        'Destination.CcAddresses.member.1': 'cc1@example.com',
        'Destination.CcAddresses.member.2': 'cc2@example.com',
        'Destination.CcAddresses.member.3': 'cc3@example.com',
        'Destination.CcAddresses.member.4': 'cc4@example.com',
        'Destination.BccAddresses.member.1': 'bcc@exmaple.com',
    }
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


async def test_custom_headers(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    await ses.send_email(
        'testing@sender.com',
        'test email',
        ['testing@example.com'],
        'this is a test email',
        unsubscribe_link='https://example.com/unsubscribe',
        configuration_set='testing-set',
        message_tags={'foo': 'bar', 'another': 1},
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['email'] == {
        'Subject': 'test email',
        'From': 'testing@sender.com',
        'To': 'testing@example.com',
        'List-Unsubscribe': '<https://example.com/unsubscribe>',
        'X-SES-CONFIGURATION-SET': 'testing-set',
        'X-SES-MESSAGE-TAGS': 'foo=bar, another=1',
        'Content-Transfer-Encoding': '7bit',
        'MIME-Version': '1.0',
        'payload': [{'Content-Type': 'text/plain', 'payload': 'this is a test email\n'}],
    }


async def test_webhook_open(client: AsyncClient):
    message = {'eventType': 'Open', 'mail': {'messageId': 'testing-123'}, 'open': {'ipAddress': '1.2.3.4'}}
    d = {'Type': 'Notification', 'Message': json.dumps(message)}
    info = await SesWebhookInfo.build('Basic ZEdWemRHbHVadz09', json.dumps(d), base64.b64encode(b'testing'), client)
    assert info.message_id == 'testing-123'
    assert info.event_type == 'open'
    assert info.unsubscribe is False
    assert info.extra == {'ip_address': '1.2.3.4'}


async def test_webhook_bounce(client: AsyncClient):
    message = {'eventType': 'Bounce', 'mail': {'messageId': 'testing-123'}, 'bounce': {'bounceType': 'other'}}
    d = {'Type': 'Notification', 'Message': json.dumps(message)}
    info = await SesWebhookInfo.build('Basic ZEdWemRHbHVadz09', json.dumps(d), base64.b64encode(b'testing'), client)
    assert info.message_id == 'testing-123'
    assert info.event_type == 'bounce'
    assert info.unsubscribe is False
    assert info.extra == {'bounce_type': 'other'}


async def test_webhook_complaint(client: AsyncClient):
    message = {'eventType': 'Complaint', 'mail': {'messageId': 'testing-123'}}
    d = {'Type': 'Notification', 'Message': json.dumps(message)}
    info = await SesWebhookInfo.build('Basic ZEdWemRHbHVadz09', json.dumps(d), base64.b64encode(b'testing'), client)
    assert info.message_id == 'testing-123'
    assert info.event_type == 'complaint'
    assert info.unsubscribe is True
    assert info.extra == {}


async def test_webhook_bad_auth(client: AsyncClient):
    d = {'Type': 'Notification', 'Message': '{}'}
    with pytest.raises(SesWebhookAuthError, match='Invalid basic auth'):
        await SesWebhookInfo.build('Basic foobar', json.dumps(d), base64.b64encode(b'testing'), client)


async def test_webhook_subscribe(client: AsyncClient, aws: DummyServer):
    d = {'Type': 'SubscriptionConfirmation', 'SubscribeURL': f'{aws.server_name}/status/200/'}
    info = await SesWebhookInfo.build('Basic ZEdWemRHbHVadz09', json.dumps(d), base64.b64encode(b'testing'), client)
    assert info is None
    assert aws.log == ['GET /status/200/ > 200']


real_ses_test = pytest.mark.skipif(not os.getenv('TEST_AWS_ACCESS_KEY'), reason='requires TEST_AWS_ACCESS_KEY env var')


@real_ses_test
async def test_send_real():
    access_key = os.getenv('TEST_AWS_ACCESS_KEY')
    secret_key = os.getenv('TEST_AWS_SECRET_KEY')
    async with AsyncClient() as client:
        ses = SesClient(client, SesConfig(access_key, secret_key, 'eu-west-1'))

        message_id = await ses.send_email(
            'testing@scolvin.com',
            'test email',
            [Recipient('success@simulator.amazonses.com', 'Test', 'Person')],
            'this is a test email',
            html_body='This is a <b>test</b> email.',
        )
        assert len(message_id) > 20
