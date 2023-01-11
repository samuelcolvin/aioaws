import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import chain
from typing import TYPE_CHECKING, Any, AsyncIterable, Dict, List, Optional, Union
from xml.etree import ElementTree

from httpx import URL, AsyncClient
from pydantic import BaseModel, validator

from ._utils import ManyTasks, pretty_xml, utcnow
from .core import AwsClient, RequestError

if TYPE_CHECKING:
    from ._types import S3ConfigProtocol

__all__ = 'S3Client', 'S3Config', 'S3File'

# rounding of download link expiry time, this allows the CDN to efficiently cache download links
expiry_rounding = 100
# removing xmlns="http://s3.amazonaws.com/doc/2006-03-01/" from xml makes it much easier to parse
xmlns = 'http://s3.amazonaws.com/doc/2006-03-01/'
xmlns_re = re.compile(f' xmlns="{re.escape(xmlns)}"'.encode())


@dataclass
class S3Config:
    aws_access_key: str
    aws_secret_key: str
    aws_region: str
    aws_s3_bucket: str
    # custom host to connect with
    aws_host: Optional[str] = None


class S3File(BaseModel):
    key: str
    last_modified: datetime
    size: int
    e_tag: str
    storage_class: str

    @validator('e_tag')
    def set_ts_now(cls, v: str) -> str:
        return v.strip('"')

    class Config:
        @classmethod
        def alias_generator(cls, string: str) -> str:
            return ''.join(word.capitalize() for word in string.split('_'))


class S3Client:
    __slots__ = '_config', '_aws_client'

    def __init__(self, http_client: AsyncClient, config: 'S3ConfigProtocol'):
        self._aws_client = AwsClient(http_client, config, 's3')
        self._config = config

    async def list(self, prefix: Optional[str] = None) -> AsyncIterable[S3File]:
        """
        List S3 files with the given prefix.

        https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html
        """
        assert prefix is None or not prefix.startswith('/'), 'the prefix to filter by should not start with "/"'
        continuation_token = None

        while True:
            params = {'list-type': 2, 'prefix': prefix, 'continuation-token': continuation_token}
            r = await self._aws_client.get(params={k: v for k, v in params.items() if v is not None})

            xml_root = ElementTree.fromstring(xmlns_re.sub(b'', r.content))
            for c in xml_root.findall('Contents'):
                yield S3File.parse_obj({v.tag: v.text for v in c})
            if (t := xml_root.find('IsTruncated')) is not None and t.text == 'false':
                break

            if (t := xml_root.find('NextContinuationToken')) is not None:
                continuation_token = t.text
            else:
                raise RuntimeError(f'unexpected response from S3:\n{pretty_xml(r.content)}')

    async def delete(self, *files: Union[str, S3File]) -> List[str]:
        """
        Delete one or more files, based on keys.
        """
        tasks = ManyTasks()
        chunk_size = 1000
        for i in range(0, len(files), chunk_size):
            tasks.add(self._delete_1000_files(*files[i : i + chunk_size]))

        results = await tasks.finish()
        return list(chain(*results))

    async def upload(self, file_path: str, content: bytes, *, content_type: Optional[str] = None) -> None:
        assert not file_path.startswith('/'), 'file_path must not start with /'
        parts = file_path.rsplit('/', 1)

        if content_type is None:
            content_type, _ = mimetypes.guess_type(file_path)

        d = self.signed_upload_url(
            path=f'{parts[0]}/' if len(parts) > 1 else '',
            filename=parts[-1],
            content_type=content_type or 'application/octet-stream',
            size=len(content),
            expires=datetime.utcnow() + timedelta(minutes=30),
        )
        await self._aws_client.raw_post(d['url'], expected_status=204, data=d['fields'], files={'file': content})

    async def delete_recursive(self, prefix: Optional[str]) -> List[str]:
        """
        Delete files starting with a specific prefix.
        """
        files = []
        tasks = ManyTasks()
        async for f in self.list(prefix):
            files.append(f)
            if len(files) == 1000:
                tasks.add(self._delete_1000_files(*files))
                files = []

        if files:
            tasks.add(self._delete_1000_files(*files))
        results = await tasks.finish()
        return list(chain(*results))

    async def _delete_1000_files(self, *files: Union[str, S3File]) -> List[str]:
        """
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObjects.html
        """
        assert len(files) <= 1000, f'_delete_1000_files can delete 1000 files max, not {len(files)}'
        xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Delete xmlns="{xmlns}">'
            f' {"".join(f"<Object><Key>{to_key(k)}</Key></Object>" for k in files)}'
            f'</Delete>'
        )
        r = await self._aws_client.post('', data=xml.encode(), params=dict(delete=1), content_type='text/xml')
        xml_root = ElementTree.fromstring(xmlns_re.sub(b'', r.content))
        return [k.find('Key').text for k in xml_root]  # type: ignore

    def signed_download_url(self, path: str, version: Optional[str] = None, max_age: int = 30) -> str:
        """
        Sign a path to authenticate download.

        The url is valid for between max_age seconds and max_age + expiry_rounding seconds.

        https://docs.aws.amazon.com/AmazonS3/latest/dev/RESTAuthentication.html#RESTAuthenticationQueryStringAuth
        """
        assert not path.startswith('/'), 'path should not start with /'
        url = URL(f'{self._aws_client.endpoint}/{path}')
        url = self._aws_client.add_signed_download_params('GET', url, max_age)
        if version:
            url = url.copy_add_param('v', version)
        return str(url)

    async def download(self, file: Union[str, S3File], version: Optional[str] = None) -> bytes:
        if isinstance(file, str):
            path = file
        else:
            path = file.key

        url = self.signed_download_url(path, version=version)
        r = await self._aws_client.client.get(url)
        if r.status_code == 200:
            return r.content
        else:
            raise RequestError(r)

    def signed_upload_url(
        self,
        *,
        path: str,
        filename: str,
        content_type: str,
        size: int,
        content_disp: bool = True,
        expires: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
        """
        assert path == '' or path.endswith('/'), 'path must be empty or end with "/"'
        assert not path.startswith('/'), 'path must not start with "/"'
        key = path + filename
        policy_conditions = [
            {'bucket': self._config.aws_s3_bucket},
            {'key': key},
            {'content-type': content_type},
            ['content-length-range', size, size],
        ]

        content_disp_fields = {}
        if content_disp:
            content_disp_fields = {'Content-Disposition': f'attachment; filename="{filename}"'}
            policy_conditions.append(content_disp_fields)

        now = utcnow()
        policy_conditions += self._aws_client.upload_extra_conditions(now)

        policy = {
            'expiration': f'{expires or now + timedelta(seconds=60):%Y-%m-%dT%H:%M:%SZ}',
            'conditions': policy_conditions,
        }
        b64_policy = base64.b64encode(json.dumps(policy).encode()).decode()

        fields = {
            'Key': key,
            'Content-Type': content_type,
            **content_disp_fields,
            'Policy': b64_policy,
            **self._aws_client.signed_upload_fields(now, b64_policy),
        }
        return dict(url=f'{self._aws_client.endpoint}/', fields=fields)


def to_key(sf: Union[S3File, str]) -> str:
    if isinstance(sf, str):
        return sf
    elif isinstance(sf, S3File):
        return sf.key
    else:
        raise TypeError('must be a string or S3File object')
