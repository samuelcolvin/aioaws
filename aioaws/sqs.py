from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, Mapping, Optional, Union

from httpx import AsyncClient, Timeout
from pydantic import BaseModel, Field

from .core import AWSV4AuthFlow


class AWSAuthConfig(BaseModel):
    aws_access_key: str
    aws_secret_key: str
    aws_region: str


class SQSMessage(BaseModel):
    message_id: str
    receipt_handle: str
    md5_of_body: str
    body: str
    attributes: Mapping[str, Any]


class PollConfig(BaseModel):
    wait_time: int = Field(10, gt=0)
    max_messages: int = Field(1, ge=1, le=10)


@dataclass
class _QueueName:
    name: str


@dataclass
class _QueueURL:
    url: str


MAX_VISIBILITY_TIMEOUT = 12 * 60 * 60  # 12 hours in seconds


class SQSClient:
    def __init__(
        self,
        queue_name_or_url: str,
        auth: AWSAuthConfig,
        *,
        client: AsyncClient,
    ) -> None:
        self._queue_name_or_url: Union[_QueueName, _QueueURL]
        if queue_name_or_url[:4] == 'http':
            self._queue_name_or_url = _QueueURL(queue_name_or_url)
        else:
            self._queue_name_or_url = _QueueName(queue_name_or_url)
        self._client = client
        self._auth = AWSV4AuthFlow(
            aws_access_key=auth.aws_access_key,
            aws_secret_key=auth.aws_secret_key,
            region=auth.aws_region,
            service='sqs',
        )
        self._service_url = f'https://sqs.{auth.aws_region}.amazonaws.com'

    async def _get_queue_url_from_name_and_region(
        self,
        queue_name: str,
        client: AsyncClient,
        auth: AWSV4AuthFlow,
    ) -> str:
        resp = await client.get(
            url=self._service_url,
            params={
                'Action': 'GetQueueUrl',
                'QueueName': queue_name,
            },
            auth=auth,
            headers={'Accept': 'application/json'},
        )
        resp.raise_for_status()
        return resp.json()['GetQueueUrlResponse']['GetQueueUrlResult']['QueueUrl']

    async def _get_queue_url(self) -> str:
        if isinstance(self._queue_name_or_url, _QueueName):
            self._queue_name_or_url = _QueueURL(
                await self._get_queue_url_from_name_and_region(
                    self._queue_name_or_url.name,
                    self._client,
                    auth=self._auth,
                )
            )
        return self._queue_name_or_url.url

    async def poll(
        self,
        *,
        config: Optional[PollConfig] = None,
    ) -> AsyncIterator[Iterable[SQSMessage]]:
        config = config or PollConfig()
        queue_url = await self._get_queue_url()
        while True:
            resp = await self._client.get(
                url=queue_url,
                params={
                    'Action': 'ReceiveMessage',
                    'MaxNumberOfMessages': config.max_messages,
                    'WaitTimeSeconds': config.wait_time,
                },
                headers={
                    'Accept': 'application/json',
                },
                timeout=Timeout(
                    5,  # htppx's default timeout
                    # arbitrary selection of 1.5x wait time
                    # to avoid http timeouts while long polling
                    read=config.wait_time * 1.5,
                ),
                auth=self._auth,
            )
            resp.raise_for_status()
            yield [
                SQSMessage.construct(
                    message_id=message_data['MessageId'],
                    receipt_handle=message_data['ReceiptHandle'],
                    md5_of_body=message_data['MD5OfBody'],
                    body=message_data['Body'],
                    attributes=message_data['Attributes'],
                )
                for message_data in resp.json()['ReceiveMessageResponse']['ReceiveMessageResult']['messages'] or ()
            ]

    async def change_visibility(self, message: SQSMessage, timeout: int) -> None:
        queue_url = await self._get_queue_url()
        if timeout >= MAX_VISIBILITY_TIMEOUT:
            raise ValueError(f'timeout value range is 0 to {MAX_VISIBILITY_TIMEOUT}, got {timeout}')
        await self._client.post(
            url=queue_url,
            params={
                'Action': 'ChangeMessageVisibility',
                'VisibilityTimeout': timeout,
                'ReceiptHandle': message.receipt_handle,
            },
            auth=self._auth,
            headers={
                'Accept': 'application/json',
            },
        )

    async def delete_message(self, message: SQSMessage) -> None:
        queue_url = await self._get_queue_url()
        resp = await self._client.post(
            url=queue_url,
            params={
                'Action': 'DeleteMessage',
                'ReceiptHandle': message.receipt_handle,
            },
            auth=self._auth,
            headers={
                'Accept': 'application/json',
            },
        )
        resp.raise_for_status()


@asynccontextmanager
async def create_sqs_client(
    queue: str,
    auth: AWSAuthConfig,
    *,
    client: Optional[AsyncClient] = None,
) -> AsyncIterator[SQSClient]:
    async with AsyncExitStack() as stack:
        if client is None:
            client = await stack.enter_async_context(AsyncClient())
            assert client is not None  # for mypy
        yield SQSClient(
            queue_name_or_url=queue,
            auth=auth,
            client=client,
        )
