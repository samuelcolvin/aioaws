import base64
import json
import re
from datetime import datetime

import pytest
from dirty_equals import IsStr
from foxglove.test_server import DummyServer
from httpx import AsyncClient

from aioaws.ses import SesAttachment, SesClient, SesConfig, SesRecipient, SesWebhookInfo
from aioaws.sns import SnsWebhookError

from .conftest import AWS

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
        'RawMessage.Data': IsStr(),
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
        'test with attachment £££ more',
        ['testing@recipient.com'],
        'this is a test email',
        attachments=[SesAttachment(file=b'some binary data', name='testing.txt', mime_type='text/plain')],
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['email'] == {
        'Subject': 'test with attachment £££ more',
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
    raw_body = base64.b64decode(eml['body']['RawMessage.Data'].encode())

    assert re.fullmatch(
        (
            br'Subject: test with attachment =\?utf-8\?b\?wqPCo8Kj\?= more\n'
            br'From: testing@sender\.com\n'
            br'To: testing@recipient\.com\n'
            br'MIME-Version: 1\.0\n'
            br'Content-Type: multipart/mixed; boundary="===============(\d+)=="\n\n'
            br'--===============\1==\n'
            br'Content-Type: text/plain; charset="utf-8"\n'
            br'Content-Transfer-Encoding: 7bit\n\n'
            br'this is a test email\n\n'
            br'--===============(\d+)==\n'
            br'Content-Type: text/plain\n'
            br'MIME-Version: 1\.0\n'
            br'Content-Transfer-Encoding: base64\n'
            br'Content-Disposition: attachment; filename="testing\.txt"\n\n'
            br'c29tZSBiaW5hcnkgZGF0YQ==\n\n'
            br'--===============\2==--\n'
        ),
        raw_body,
    )


async def test_attachment_path(client: AsyncClient, aws: DummyServer, tmp_path):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    p = tmp_path / 'testing.txt'
    p.write_text('hello')

    await ses.send_email(
        'testing@sender.com',
        'test with attachment',
        ['testing@recipient.com'],
        html_body='<b>html body</b>',
        attachments=[SesAttachment(file=p)],
    )
    assert len(aws.app['emails']) == 1
    email = aws.app['emails'][0]['email']
    assert email == {
        'Subject': 'test with attachment',
        'From': 'testing@sender.com',
        'To': 'testing@recipient.com',
        'MIME-Version': '1.0',
        'payload': [
            {'Content-Type': 'text/plain', 'payload': '\n'},
            {'Content-Type': 'text/html', 'payload': '<b>html body</b>\n'},
            {
                'Content-Type': 'text/plain',
                'payload': 'hello',
                'Content-Disposition': 'attachment; filename="testing.txt"',
            },
        ],
    }


async def test_send_names(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    await ses.send_email(
        'testing@sender.com',
        'test email',
        [SesRecipient('testing@example.com', 'John', 'Doe')],
        'this is a test email',
        cc=[
            SesRecipient('cc1@example.com'),
            SesRecipient('cc2@example.com', 'CC2'),
            SesRecipient('cc3@example.com', None, 'CC3'),
            SesRecipient('cc4@example.com', 'Anna, Bob', 'CC4'),
        ],
        bcc=['bcc@exmaple.com'],
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['body'] == {
        'Action': 'SendRawEmail',
        'Source': 'testing@sender.com',
        'RawMessage.Data': IsStr(),
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


async def test_attachment_email_with_html(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    await ses.send_email(
        'testing@sender.com',
        'the subject',
        ['testing@recipient.com'],
        'this is a test email',
        html_body='this is the <b>html body</b>.',
        attachments=[SesAttachment(file=b'some attachment', name='testing.txt', mime_type='application/pdf')],
    )
    assert len(aws.app['emails']) == 1
    eml = aws.app['emails'][0]
    assert eml['email']['Subject'] == 'the subject'
    raw_body = base64.b64decode(eml['body']['RawMessage.Data'].encode())
    assert re.fullmatch(
        (
            br'Subject: the subject\n'
            br'From: testing@sender\.com\n'
            br'To: testing@recipient\.com\n'
            br'MIME-Version: 1\.0\n'
            br'Content-Type: multipart/mixed; boundary="===============(\d+)=="\n\n'
            br'--===============\1==\n'
            br'Content-Type: multipart/alternative;\n'
            br' boundary="===============(\d+)=="\n\n'
            br'--===============\2==\n'
            br'Content-Type: text/plain; charset="utf-8"\n'
            br'Content-Transfer-Encoding: 7bit\n\n'
            br'this is a test email\n\n'
            br'--===============\2==\n'
            br'Content-Type: text/html; charset="utf-8"\n'
            br'Content-Transfer-Encoding: 7bit\n'
            br'MIME-Version: 1\.0\n\n'
            br'this is the <b>html body</b>\.\n\n'
            br'--===============\2==--\n\n'
            br'--===============\1==\n'
            br'Content-Type: text/plain\n'
            br'MIME-Version: 1\.0\n'
            br'Content-Transfer-Encoding: base64\n'
            br'Content-Disposition: attachment; filename="testing\.txt"\n\n'
            br'c29tZSBhdHRhY2htZW50\n\n'
            br'--===============\1==--\n'
        ),
        raw_body,
    )


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
        smtp_headers={'Spam': 'Cake'},
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
        'Spam': 'Cake',
        'payload': [{'Content-Type': 'text/plain', 'payload': 'this is a test email\n'}],
    }


async def test_inline_attachment(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))

    await ses.send_email(
        'testing@sender.com',
        'the subject',
        ['testing@recipient.com'],
        'this is a test email',
        html_body='this is the <b>html body</b>.',
        attachments=[SesAttachment(file=b'some attachment', name='foobar.txt', content_id='<testing-content-id>')],
    )
    assert len(aws.app['emails']) == 1
    assert aws.app['emails'][0]['email']['payload'] == [
        {
            'Content-Type': 'text/plain',
            'payload': 'this is a test email\n',
        },
        {
            'Content-Type': 'text/html',
            'payload': 'this is the <b>html body</b>.\n',
        },
        {
            'Content-Type': 'text/plain',
            'payload': 'some attachment',
            'Content-Disposition': 'inline; filename="foobar.txt"',
            'Content-ID': '<testing-content-id>',
        },
    ]


async def test_encoded_unsub(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))
    unsub_link = 'https://www.example.com/unsubscrible?blob=?blob=$MzMgMTYwMTY3MDEyOCBMMzcbN_nhcDZNg-6D=='
    await ses.send_email(
        'testing@sender.com',
        'test email',
        ['testing@recipient.com'],
        'this is a test email',
        unsubscribe_link=unsub_link,
    )
    email = aws.app['emails'][0]['email']
    assert email['List-Unsubscribe'] == f'<{unsub_link}>'


async def test_no_recipients(client: AsyncClient, aws: DummyServer):
    ses = SesClient(client, SesConfig('test_access_key', 'test_secret_key', 'testing-region-1'))
    with pytest.raises(TypeError, match='either "to", "cc", or "bcc" must be provided'):
        await ses.send_email('testing@sender.com', 'test email', None, 'xx')

    assert aws.log == []


async def test_webhook_open(client: AsyncClient, build_sns_webhook):
    message = {'eventType': 'Open', 'mail': {'messageId': 'testing-123'}, 'open': {'ipAddress': '1.2.3.4'}}
    info = await SesWebhookInfo.build(build_sns_webhook(message), client)
    assert info.message_id == 'testing-123'
    assert info.event_type == 'open'
    assert info.timestamp is None
    assert info.unsubscribe is False
    assert info.details == {'ipAddress': '1.2.3.4'}
    assert info.full_message == message


async def test_webhook_bounce(client: AsyncClient, build_sns_webhook):
    message = {
        'eventType': 'Bounce',
        'mail': {'messageId': 'testing-123', 'tags': {'ses:operation': ['SendRawEmail']}},
        'bounce': {'bounceType': 'other'},
    }
    info = await SesWebhookInfo.build(build_sns_webhook(message).encode(), client)
    assert info.message_id == 'testing-123'
    assert info.event_type == 'bounce'
    assert info.unsubscribe is False
    assert info.details == {'bounceType': 'other'}
    assert info.tags == {'ses:operation': 'SendRawEmail'}


async def test_webhook_complaint(client: AsyncClient, build_sns_webhook):
    message = {'eventType': 'Complaint', 'mail': {'messageId': 'testing-123'}}
    info = await SesWebhookInfo.build(build_sns_webhook(message), client)
    assert info.message_id == 'testing-123'
    assert info.event_type == 'complaint'
    assert info.unsubscribe is True


async def test_webhook_ts(client: AsyncClient, build_sns_webhook):
    message = {'eventType': 'Open', 'mail': {'messageId': 'testing-123', 'timestamp': '2020-06-05T12:30:20'}}
    info = await SesWebhookInfo.build(build_sns_webhook(message), client)
    assert info.timestamp == datetime(2020, 6, 5, 12, 30, 20)


async def test_webhook_bad_auth(client: AsyncClient):
    d = {
        'Type': 'Notification',
        'SigningCertURL': 'https://sns.eu-west-2.amazonaws.com/SimpleNotificationService-123.pem',
        'Signature': base64.b64encode(b'testing').decode(),
        'Message': '{}',
    }
    with pytest.raises(SnsWebhookError, match='invalid signature'):
        await SesWebhookInfo.build(json.dumps(d), client)


async def test_webhook_no_json(client: AsyncClient, build_sns_webhook):
    info = await SesWebhookInfo.build(build_sns_webhook('foobar'), client)
    assert info is None


async def test_webhook_bad_signing_url(client: AsyncClient, build_sns_webhook):
    with pytest.raises(SnsWebhookError, match='invalid SigningCertURL "http://www.example.com/testing"'):
        await SesWebhookInfo.build(build_sns_webhook({}, sig_url='http://www.example.com/testing'), client)


async def test_webhook_bad_response(client: AsyncClient, build_sns_webhook):
    with pytest.raises(SnsWebhookError, match='unexpected response from'):
        await SesWebhookInfo.build(build_sns_webhook({}, sig_url='https://sns.eu-west-2.amazonaws.com/bad.pem'), client)


async def test_webhook_invalid_payload(client: AsyncClient, build_sns_webhook):
    with pytest.raises(SnsWebhookError, match='invalid payload'):
        await SesWebhookInfo.build(build_sns_webhook({}, event_type='foobar'), client)


async def test_webhook_invalid_signature_base64(client: AsyncClient, build_sns_webhook):
    with pytest.raises(SnsWebhookError, match='invalid payload'):
        await SesWebhookInfo.build(build_sns_webhook({}, signature='testing'), client)


async def test_webhook_subscribe(client: AsyncClient, aws: DummyServer, mocker):
    mocker.patch('aioaws.sns.x509.load_pem_x509_certificate')
    d = {
        'Type': 'SubscriptionConfirmation',
        'SigningCertURL': 'https://sns.eu-west-2.amazonaws.com/SimpleNotificationService-123.pem',
        'Signature': base64.b64encode(b'testing').decode(),
        'SubscribeURL': 'https://sns.eu-west-2.amazonaws.com/?Action=1234',
    }
    info = await SesWebhookInfo.build(json.dumps(d), client)
    assert info is None
    assert aws.log == ['GET /sns/certs/ > 200', 'GET /status/200/?Action=1234 > 200']


async def test_real_send(real_aws: AWS):
    async with AsyncClient() as client:
        ses = SesClient(client, SesConfig(real_aws.access_key, real_aws.secret_key, 'eu-west-1'))

        message_id = await ses.send_email(
            'testing@scolvin.com',
            'test email',
            [SesRecipient('success@simulator.amazonses.com', 'Test', 'Person')],
            'this is a test email',
            html_body='This is a <b>test</b> email.',
        )
        assert len(message_id) > 20
