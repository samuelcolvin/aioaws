from typing import AsyncGenerator, List, Optional

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from aioaws.sqs import AWSAuthConfig, SQSClient, SQSMessage

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
                'ReceiveMessageResponse': {
                    'ReceiveMessageResult': {
                        'messages': [
                            {
                                'MessageId': 'message-id-1234',
                                'ReceiptHandle': 'receipt_handle',
                                'MD5OfBody': 'body-md5-123',
                                'Body': 'foo bar',
                                'Attributes': {},
                            }
                        ]
                    }
                }
            },
        )

    handler = stateful_handler()
    await handler.__anext__()  # prime the generator

    client = AsyncClient(transport=MockTransport(handler.asend))

    queue_url = 'https://sqs.us-east-2.amazonaws.com/123456789012/MyQueue'

    sqs = SQSClient(
        queue_name_or_url=queue_url,
        auth=AWSAuthConfig(
            aws_access_key='test_access_key',
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


async def test_change_visbility_timeout() -> None:
    async def stateful_handler() -> AsyncGenerator[Optional[Response], Request]:
        req = yield None
        request_url = req.url.copy_with(params={})
        assert request_url == queue_url
        # receiving messages is tested elewhere, we just do a basic check here
        assert req.url.params['Action'] == 'ReceiveMessage'
        req = yield Response(
            status_code=200,
            json={
                'ReceiveMessageResponse': {
                    'ReceiveMessageResult': {
                        'messages': [
                            {
                                'MessageId': 'message-id-1234',
                                'ReceiptHandle': 'receipt_handle',
                                'MD5OfBody': 'body-md5-123',
                                'Body': 'foo bar',
                                'Attributes': {},
                            }
                        ]
                    }
                }
            },
        )
        # now we should get a request to change the visibility timeout
        assert request_url == queue_url
        request_url = req.url.copy_with(params={})
        assert request_url == queue_url
        expected_params = {'Action': 'ChangeMessageVisibility', 'VisibilityTimeout': '1'}
        for param, expected_val in expected_params.items():
            assert req.url.params[param] == expected_val
        assert req.headers['Accept'] == 'application/json'
        # not checking auth header values, tested elsewhere
        expected_auth_headers = {'x-amz-date', 'authorization', 'x-amz-content-sha256'}
        for header in expected_auth_headers:
            assert header in req.headers
        req = yield Response(
            status_code=200,
            json={},  # we don't exepct any particular response
        )

    handler = stateful_handler()
    await handler.__anext__()  # prime the generator

    client = AsyncClient(transport=MockTransport(handler.asend))

    queue_url = 'https://sqs.us-east-2.amazonaws.com/123456789012/MyQueue'

    sqs = SQSClient(
        queue_name_or_url=queue_url,
        auth=AWSAuthConfig(
            aws_access_key='test_access_key',
            aws_secret_key='test_secret_key',
            aws_region='testing-region-1',
        ),
        client=client,
    )

    # receive 1 batch of messages
    async for received_messages in sqs.poll():
        for message in received_messages:
            await sqs.change_visibility(message, 1)
        break

    try:
        await handler.__anext__()
    except StopAsyncIteration:
        pass
    else:
        raise AssertionError('Missing API calls')


async def test_delete_message() -> None:
    async def stateful_handler() -> AsyncGenerator[Optional[Response], Request]:
        req = yield None
        request_url = req.url.copy_with(params={})
        assert request_url == queue_url
        # receiving messages is tested elewhere, we just do a basic check here
        assert req.url.params['Action'] == 'ReceiveMessage'
        req = yield Response(
            status_code=200,
            json={
                'ReceiveMessageResponse': {
                    'ReceiveMessageResult': {
                        'messages': [
                            {
                                'MessageId': 'message-id-1234',
                                'ReceiptHandle': 'receipt_handle',
                                'MD5OfBody': 'body-md5-123',
                                'Body': 'foo bar',
                                'Attributes': {},
                            }
                        ]
                    }
                }
            },
        )
        # now we should get a request to delete the message
        assert request_url == queue_url
        request_url = req.url.copy_with(params={})
        assert request_url == queue_url
        expected_params = {'Action': 'DeleteMessage', 'ReceiptHandle': 'receipt_handle'}
        for param, expected_val in expected_params.items():
            assert req.url.params[param] == expected_val
        assert req.headers['Accept'] == 'application/json'
        # not checking auth header values, tested elsewhere
        expected_auth_headers = {'x-amz-date', 'authorization', 'x-amz-content-sha256'}
        for header in expected_auth_headers:
            assert header in req.headers
        req = yield Response(
            status_code=200,
            json={},  # we don't exepct any particular response
        )

    handler = stateful_handler()
    await handler.__anext__()  # prime the generator

    client = AsyncClient(transport=MockTransport(handler.asend))

    queue_url = 'https://sqs.us-east-2.amazonaws.com/123456789012/MyQueue'

    sqs = SQSClient(
        queue_name_or_url=queue_url,
        auth=AWSAuthConfig(
            aws_access_key='test_access_key',
            aws_secret_key='test_secret_key',
            aws_region='testing-region-1',
        ),
        client=client,
    )

    # receive 1 batch of messages
    async for received_messages in sqs.poll():
        for message in received_messages:
            await sqs.delete_message(message)
        break

    try:
        await handler.__anext__()
    except StopAsyncIteration:
        pass
    else:
        raise AssertionError('Missing API calls')


async def test_get_queue_url() -> None:
    async def stateful_handler() -> AsyncGenerator[Optional[Response], Request]:
        req = yield None
        # check that we request the queue url
        request_url = req.url.copy_with(params={})
        assert request_url == 'https://sqs.testing-region-1.amazonaws.com'
        expected_params = {'Action': 'GetQueueUrl', 'QueueName': 'test'}
        for param, expected_val in expected_params.items():
            assert req.url.params[param] == expected_val
        assert req.headers['Accept'] == 'application/json'
        # not checking auth header values, tested elsewhere
        expected_auth_headers = {'x-amz-date', 'authorization', 'x-amz-content-sha256'}
        for header in expected_auth_headers:
            assert header in req.headers
        queue_url = 'https://sqs.us-east-2.amazonaws.com/123456789012/test'
        req = yield Response(
            status_code=200,
            json={
                'GetQueueUrlResponse': {
                    'GetQueueUrlResult': {
                        'QueueUrl': queue_url,
                    }
                }
            },
        )

        # receiving messages is tested elewhere, we just do a basic check here
        request_url = req.url.copy_with(params={})
        assert request_url == queue_url
        assert req.url.params['Action'] == 'ReceiveMessage'
        req = yield Response(
            status_code=200,
            json={
                'ReceiveMessageResponse': {
                    'ReceiveMessageResult': {
                        'messages': [
                            {
                                'MessageId': 'message-id-1234',
                                'ReceiptHandle': 'receipt_handle',
                                'MD5OfBody': 'body-md5-123',
                                'Body': 'foo bar',
                                'Attributes': {},
                            }
                        ]
                    }
                }
            },
        )

    handler = stateful_handler()
    await handler.__anext__()  # prime the generator

    client = AsyncClient(transport=MockTransport(handler.asend))

    queue_name = 'test'

    sqs = SQSClient(
        queue_name_or_url=queue_name,
        auth=AWSAuthConfig(
            aws_access_key='test_access_key',
            aws_secret_key='test_secret_key',
            aws_region='testing-region-1',
        ),
        client=client,
    )

    # receive 1 batch of messages
    async for _ in sqs.poll():
        break

    try:
        await handler.__anext__()
    except StopAsyncIteration:
        pass
    else:
        raise AssertionError('Missing API calls')
