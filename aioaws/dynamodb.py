from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Any, AsyncIterable, Dict, Optional, Union
from httpx import AsyncClient
from .core import AwsClient, RequestError

if TYPE_CHECKING:
    from ._types import DynamoDBConfigProtocol

__all__ = ('DynamoDBClient',)


@dataclass
class DynamoDBConfig:
    aws_access_key: str
    aws_secret_key: str
    aws_region: str
    # custom host to connect with
    aws_host: Optional[str] = None


class DynamoDBClient:
    __slots__ = '_config', '_aws_client'

    def __init__(self, http_client: AsyncClient, config: "DynamoDBConfigProtocol"):
        self._aws_client = AwsClient(http_client, config, 'dynamodb')
        self._config = config

    async def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Put an item into the specified DynamoDB table.
        """
        payload = {"TableName": table_name, "Item": item}
        response = await self._aws_client.post(
            "/",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/x-amz-json-1.0",
                "X-Amz-Target": "DynamoDB_20120810.PutItem",
            },
        )
        return response.json()

    async def delete_item(self, table_name: str, key: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delete an item from the specified DynamoDB table.
        """
        payload = {"TableName": table_name, "Key": key}
        response = await self._aws_client.post(
            "/",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/x-amz-json-1.0",
                "X-Amz-Target": "DynamoDB_20120810.DeleteItem",
            },
        )
        return response.json()

    async def get_item(self, table_name: str, key: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get an item from the specified DynamoDB table.
        """
        payload = {"TableName": table_name, "Key": key}
        response = await self._aws_client.post(
            "/",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/x-amz-json-1.0",
                "X-Amz-Target": "DynamoDB_20120810.GetItem",
            },
        )
        return response.json()

    async def query(
        self, table_name: str, expression: str, expression_values: Dict[str, Any], **kwargs: Any
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Query the specified DynamoDB table and return an async iterable.
        """
        last_evaluated_key = None
        while True:
            payload = {
                "TableName": table_name,
                "KeyConditionExpression": expression,
                "ExpressionAttributeValues": expression_values,
                **kwargs,
            }
            if last_evaluated_key:
                payload["ExclusiveStartKey"] = last_evaluated_key

            response = await self._aws_client.post(
                "/",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/x-amz-json-1.0",
                    "X-Amz-Target": "DynamoDB_20120810.Query",
                }
            )
            response_data = response.json()

            # Yield the items from the current batch of results
            for item in response_data.get('Items', []):
                yield item

            # If there's more data, set the last_evaluated_key for the next loop iteration
            last_evaluated_key = response_data.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break  # No more items left to query
