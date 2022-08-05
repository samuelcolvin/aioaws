from typing import AsyncGenerator, List, Optional

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from aioaws.sqs import SQSClient, SQSClientConfig, SQSMessage

pytestmark = pytest.mark.asyncio


async def test_poll_from_queue_url() -> None:
    async def stateful_handler() -> AsyncGenerator[Optional[Response], Request]:
        req = yield None
        request_url = req.url.copy_with(params={})
        assert request_url == queue_url
        expected_params = {'Action': 'ReceiveMessage', 'MaxNumberOfMessages': '1', 'WaitTimeSeconds': '10'}
        for param, expected_val in expected_params.items():
            assert req.url.params[param] == expected_val
        assert req.headers['Accept'] == 'application/json'
        # not checking auth header values, tested elsewhere
        expected_auth_headers = {'x-amz-date', 'authorization', 'x-amz-content-sha256'}
        for header in expected_auth_headers:
            assert header in req.headers
        req = yield Response(
            status_code=200,
            json={
                'Messages': [
                    {
                        'MessageId': 'message-id-1234',
                        'ReceiptHandle': 'receipt_handle',
                        'MD5OfBody': 'body-md5-123',
                        'Body': 'foo bar',
                        'Attributes': {},
                    }
                ]
            },
        )

    handler = stateful_handler()
    await handler.__anext__()  # prime the generator

    client = AsyncClient(transport=MockTransport(handler.asend))

    queue_url = 'https://sqs.us-east-2.amazonaws.com/123456789012/MyQueue'

    sqs = SQSClient(
        queue_name_or_url=queue_url,
        config=SQSClientConfig(
            aws_access_key_id='test_access_key',
            aws_secret_key='test_secret_key',
            aws_region='testing-region-1',
        ),
        client=client,
    )

    messages: List[SQSMessage] = []

    # receive 1 batch of messages
    async for received_messages in sqs.poll():
        messages.extend(received_messages)
        break

    expected_messages = [
        SQSMessage(
            message_id='message-id-1234',
            receipt_handle='receipt_handle',
            md5_of_body='body-md5-123',
            body='foo bar',
            attributes={},
        )
    ]
    assert messages == expected_messages
