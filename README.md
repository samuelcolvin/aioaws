# aioaws

[![CI](https://github.com/samuelcolvin/aioaws/workflows/CI/badge.svg?event=push)](https://github.com/samuelcolvin/aioaws/actions?query=event%3Apush+branch%3Amain+workflow%3ACI)
[![Coverage](https://codecov.io/gh/samuelcolvin/aioaws/branch/main/graph/badge.svg)](https://codecov.io/gh/samuelcolvin/aioaws)
[![pypi](https://img.shields.io/pypi/v/aioaws.svg)](https://pypi.python.org/pypi/aioaws)
[![versions](https://img.shields.io/pypi/pyversions/aioaws.svg)](https://github.com/samuelcolvin/aioaws)
[![license](https://img.shields.io/github/license/samuelcolvin/aioaws.svg)](https://github.com/samuelcolvin/aioaws/blob/main/LICENSE)

Asyncio compatible SDK for aws services.

This library does not depend on boto, boto3 or any of the other bloated, opaque and mind thumbing AWS SDKs. Instead, it
is written from scratch to provide clean, secure and easily debuggable access to AWS services I want to use.

The library is formatted with black and includes complete type hints (mypy passes in strict-mode).

It currently supports:
* **S3** - list, delete, recursive delete, generating signed upload URLs, generating signed download URLs
* **SES** - sending emails including with attachments and multipart
* **SNS** - enough to get notifications about mail delivery from SES
* [AWS Signature Version 4](https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-auth-using-authorization-header.html)
  authentication for any AWS service (this is the only clean & modern implementation of AWS4 I know of in python, see
  [`core.py`](https://github.com/samuelcolvin/aioaws/blob/main/aioaws/core.py#L120-L175))

The only dependencies of **aioaws**, are:
* **aiofiles** - for asynchronous reading of files
* **cryptography** - for verifying SNS signatures
* **httpx** - for HTTP requests
* **pydantic** - for validating responses

## Install

```bash
pip install aioaws
```

## S3 Usage


```py
import asyncio
# requires `pip install aioaws`
from aioaws.s3 import S3Client, S3Config
from httpx import AsyncClient

# requires `pip install devtools`
from devtools import debug

async def s3_demo(client: AsyncClient):
    s3 = S3Client(client, S3Config('<access key>', '<secret key>', '<region>', 'my_bucket_name.com'))

    # upload a file:
    await s3.upload('path/to/upload-to.txt', b'this the content')

    # list all files in a bucket
    files = [f async for f in s3.list()]
    debug(files)
    """
    [
        S3File(
            key='path/to/upload-to.txt',
            last_modified=datetime.datetime(...),
            size=16,
            e_tag='...',
            storage_class='STANDARD',
        ),
    ]
    """
    # list all files with a given prefix in a bucket
    files = [f async for f in s3.list('path/to/')]
    debug(files)

    # # delete a file
    # await s3.delete('path/to/file.txt')
    # # delete two files
    # await s3.delete('path/to/file1.txt', 'path/to/file2.txt')
    # delete recursively based on a prefix
    await s3.delete_recursive('path/to/')

    # generate an upload link suitable for sending to a borwser to enabled
    # secure direct file upload (see below)
    upload_data = s3.signed_upload_url(
        path='path/to/',
        filename='demo.png',
        content_type='image/png',
        size=123,
    )
    debug(upload_data)
    """
    {
        'url': 'https://my_bucket_name.com/',
        'fields': {
            'Key': 'path/to/demo.png',
            'Content-Type': 'image/png',
            'AWSAccessKeyId': '<access key>',
            'Content-Disposition': 'attachment; filename="demo.png"',
            'Policy': '...',
            'Signature': '...',
        },
    }
    """

    # generate a temporary link to allow yourself or a client to download a file
    download_url = s3.signed_download_url('path/to/demo.png', max_age=60)
    print(download_url)
    #> https://my_bucket_name.com/path/to/demo.png?....

async def main():
    async with AsyncClient(timeout=30) as client:
        await s3_demo(client)

asyncio.run(main())
```

`upload_data` shown in the above example can be used in JS with something like this:

```js
const formData = new FormData()
for (let [name, value] of Object.entries(upload_data.fields)) {
  formData.append(name, value)
}
const fileField = document.querySelector('input[type="file"]')
formData.append('file', fileField.files[0])

const response = await fetch(upload_data.url, {method: 'POST', body: formData})
```

(in the request to get `upload_data` you would need to provide the file size and content-type in order
for them for the upload shown here to succeed)


## SES

To send an email with SES:

```py
from pathlib import Path
from httpx import AsyncClient
from aioaws.ses import SesConfig, SesClient, SesRecipient, SesAttachment

async def ses_demo(client: AsyncClient):
    ses_client = SesClient(client, SesConfig('<access key>', '<secret key>', '<region>'))

    message_id = await ses_client.send_email(
        SesRecipient('sende@example.com', 'Sender', 'Name'),
        'This is the subject',
        [SesRecipient('recipient@eample.com', 'John', 'Doe')],
        'this is the plain text body',
        html_body='<b>This is the HTML body.<b>',
        bcc=[SesRecipient(...)],
        attachments=[
            SesAttachment(b'this is content', 'attachment-name.txt', 'text/plain'),
            SesAttachment(Path('foobar.png')),
        ],
        unsubscribe_link='https:://example.com/unsubscribe',
        configuration_set='SES configuration set',
        message_tags={'ses': 'tags', 'go': 'here'},
    )
    print('SES message ID:', message_id)

async def main():
    async with AsyncClient() as client:
        await ses_demo(client)

asyncio.run(main())
```

## SNS

Receiving data about SES webhooks from SNS (assuming you're using FastAPI)

```py
from aioaws.ses import SesWebhookInfo
from aioaws.sns import SnsWebhookError
from fastapi import Request
from httpx import AsyncClient

async_client = AsyncClient...

@app.post('/ses-webhook/', include_in_schema=False)
async def ses_webhook(request: Request):
    request_body = await request.body()
    try:
        webhook_info = await SesWebhookInfo.build(request_body, async_client)
    except SnsWebhookError as e:
        debug(message=e.message, details=e.details, headers=e.headers)
        raise ...
    
    debug(webhook_info)
    ...
```

See [here](https://github.com/samuelcolvin/aioaws/blob/main/aioaws/ses.py#L196-L204)
for more information about what's provided in a `SesWebhookInfo`.
