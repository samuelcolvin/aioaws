# aioaws

[![CI](https://github.com/samuelcolvin/aioaws/workflows/CI/badge.svg?event=push)](https://github.com/samuelcolvin/aioaws/actions?query=event%3Apush+branch%3Amaster+workflow%3ACI)
[![Coverage](https://codecov.io/gh/samuelcolvin/aioaws/branch/master/graph/badge.svg)](https://codecov.io/gh/samuelcolvin/aioaws)
[![pypi](https://img.shields.io/pypi/v/aioaws.svg)](https://pypi.python.org/pypi/aioaws)
[![versions](https://img.shields.io/pypi/pyversions/aioaws.svg)](https://github.com/samuelcolvin/aioaws)
[![license](https://img.shields.io/github/license/samuelcolvin/aioaws.svg)](https://github.com/samuelcolvin/aioaws/blob/master/LICENSE)

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
  [`core.py`](https://github.com/samuelcolvin/aioaws/blob/master/aioaws/core.py#L120-L175))

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

See [here](https://github.com/samuelcolvin/aioaws/blob/master/aioaws/ses.py#L196-L204)
for more information about what's provided in a `SesWebhookInfo`.

## AWS session token support

### Description

**aioaws** has basic session token support. Session tokens are used when AWS resources obtain temporary security credentials.

The authorization flow for temporary security credentials commonly works like this:

- [IAM roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_terms-and-concepts.html), such as [service-linked roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/using-service-linked-roles.html) or [Lambda execution roles](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html), are set up and linked to infrastructure resources. These roles can have two kinds of IAM policies attached: [resource-based and identity-based policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_identity-vs-resource.html).
  - _Identity-based policies_ define interactions with other resources on AWS.
  - A _resource-based policy_ called a "role trust policy" defines how the role can be assumed.
- The AWS runtime (Fargate, Lambda, etc) requests authorization to use the role by calling the [STS `AssumeRole` API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html).
- If the requesting entity has permissions to assume the role, STS responds with [temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html) that have permissions based on the identity-based policies associated with the IAM role.
- The AWS runtime stores the temporary security credentials, typically by setting environment variables:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_SESSION_TOKEN`
- [AWS API calls with temporary credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_use-resources.html) must include the session token.
- The AWS runtime will typically rotate the temporary security credentials before they expire.

### Usage

`AWS_SESSION_TOKEN` can be added with the `S3Config.aws_session_token` attribute.

```py
S3Config('<access key>', '<secret key>', '<region>', 'my_bucket_name.com', os.getenv('AWS_SESSION_TOKEN', ''))
```

### Session token expiration

aioaws clients do not automatically rotate temporary credentials. Developers are responsible for updating
client attributes or instantiating new clients when temporary credentials expire.

Token expiration should be taken into account when generating S3 presigned URLs. As explained in the
[docs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html), "If you created a presigned
URL using a temporary token, then the URL expires when the token expires, even if the URL was created with a later
expiration time."

### Other credential sources

There are several other ways to source credentials (see the
[AWS IAM docs](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_aws-services-that-work-with-iam.html),
[AWS CLI docs](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html), and
[Boto3 docs](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html)). This project only handles AWS access keys and session tokens.
