import asyncio
import contextlib
from aioaws.s3 import S3Client, S3Config
from httpx import AsyncClient
from aioaws._utils import pretty_xml


async def s3_demo(client: AsyncClient):
    s3 = S3Client(
        client,
        S3Config(
            'hGpmIPjSKujisQEc',
            'PmG1iKDHfpwtoHKJvpl2vDfyEv47uuM0',
            'macbook-thomas',
            'testaioaws',
            "localhost:9000/testaioaws",
        ),
    )

    await s3.delete('path/testt.txt')

    async with s3.createMultipartUpload('path/testt.txt') as mpu:
        a = "123456" * 1_000_000
        b = "7890"
        await mpu.uploadPart(1, a)
        await mpu.uploadPart(3, a)

        await mpu.uploadPart(2, a)

        x = await mpu.listParts(1000)
        print(x)
        print("--")

    async with s3.createMultipartUpload('path/testt.txt') as mpu:
        x = await mpu.listParts(1000)
        print(x)
        print("--")

    async for x in s3.list():
        print(x)


async def main():
    async with AsyncClient(timeout=30) as client:
        await s3_demo(client)


asyncio.run(main())
