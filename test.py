import asyncio
from aioaws.s3 import S3Client, S3Config
from httpx import AsyncClient


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
    async with s3.createMultipartUpload('path/testt.txt') as mpu:
        a = "123456" * 1_000_000
        b = "7890"
        await mpu.uploadPart(1, a)
        await mpu.uploadPart(2, b)

async def main():
    async with AsyncClient(timeout=30) as client:
        await s3_demo(client)


asyncio.run(main())
