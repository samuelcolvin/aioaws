"""Test DynamoDB client."""

from foxglove.test_server import DummyServer
from httpx import AsyncClient
import pytest

from aiohttp import ClientSession

from aioaws.dynamodb import DynamoDBClient, DynamoDBConfig


@pytest.mark.asyncio
async def test_dynamodb(client: AsyncClient, aws: DummyServer):
    """Test DynamoDB client."""
    dynamodb_client = DynamoDBClient(client, DynamoDBConfig("testing", "testing", "testing", "testing"))
    await dynamodb_client.put_item(
        "test-table",
        {
            "id": {"S": "123"},
            "name": {"S": "test"},
            "description": {"S": "test description"},
        },
    )
    response = await dynamodb_client.get_item("test-table", {"id": {"S": "123"}})
    assert response["Item"]["name"]["S"] == "test"
    await dynamodb_client.delete_item("test-table", {"id": {"S": "123"}})
    response = await dynamodb_client.get_item("test-table", {"id": {"S": "123"}})
    assert "Item" not in response


@pytest.mark.asyncio
async def test_query(client: AsyncClient, aws: DummyServer):
    """Test DynamoDB query."""
    dynamodb_client = DynamoDBClient(
        client,
        DynamoDBConfig(
            "testing",
            "testing",
            "testing",
            "testing",
        ),
    )
    await dynamodb_client.put_item(
        "test-table",
        {
            "id": {"S": "123"},
            "name": {"S": "test"},
            "description": {"S": "test description"},
        },
    )
    async for item in dynamodb_client.query(
        "test-table",
        "id = :id",
        {
            ":id": {"S": "123"},
        },
    ):
        assert item["name"]["S"] == "test"
        break
    await dynamodb_client.delete_item("test-table", {"id": {"S": "123"}})
    async for item in dynamodb_client.query(
        "test-table",
        "id = :id",
        {
            ":id": {"S": "123"},
        },
    ):
        assert False, "should not get here"
