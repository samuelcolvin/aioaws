import base64
from email import message_from_bytes
from io import BytesIO
from typing import Any, Dict

from aiohttp import web
from aiohttp.web_response import Response
from PIL import Image, ImageDraw

s3_list_response = """\
<?xml version="1.0" ?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
    <Name>testingbucket.example.org</Name>
    <Prefix>co-slug/cat-slug/option</Prefix>
    <KeyCount>3</KeyCount>
    <MaxKeys>1000</MaxKeys>
    <IsTruncated>false</IsTruncated>
    <Contents>
        <Key>foo/bar/1.png</Key>
        <LastModified>2032-01-01T12:34:56.000Z</LastModified>
        <ETag>&quot;aaa&quot;</ETag>
        <Size>123</Size>
        <StorageClass>STANDARD</StorageClass>
    </Contents>
    <Contents>
        <Key>foo/bar/2.png</Key>
        <LastModified>2032-01-01T12:34:56.000Z</LastModified>
        <ETag>&quot;bbb&quot;</ETag>
        <Size>456</Size>
        <StorageClass>STANDARD</StorageClass>
    </Contents>
    <Contents>
        <Key>foo/bar/3.png</Key>
        <LastModified>2032-01-01T12:34:56.000Z</LastModified>
        <ETag>&quot;ccc&quot;</ETag>
        <Size>789</Size>
        <StorageClass>STANDARD</StorageClass>
    </Contents>
</ListBucketResult>"""


async def s3_root(request):
    return Response(body=s3_list_response, content_type='text/xml')


async def s3_demo_image(request):
    width, height = 2000, 1200
    stream = BytesIO()
    image = Image.new('RGB', (width, height), (50, 100, 150))
    ImageDraw.Draw(image).line((0, 0) + image.size, fill=128)
    image.save(stream, format='JPEG', optimize=True)
    return Response(body=stream.getvalue())


ses_send_response = (
    '<SendRawEmailResponse xmlns="http://ses.amazonaws.com/doc/2010-12-01/">\n'
    '  <SendRawEmailResult>\n'
    '    <MessageId>{message_id}</MessageId>\n'
    '  </SendRawEmailResult>\n'
    '  <ResponseMetadata>\n'
    '    <RequestId>{request_id}</RequestId>\n'
    '  </ResponseMetadata>\n'
    '</SendRawEmailResponse>\n'
)


def email_dict(data: Dict[str, str]) -> Dict[str, Any]:
    msg_raw = base64.b64decode(data['RawMessage.Data'])
    msg = message_from_bytes(msg_raw)
    d = dict(msg)
    d.pop('Content-Type', None)
    d['payload'] = []
    for part in msg.walk():
        if payload := part.get_payload(decode=True):
            part_info = {'Content-Type': part.get_content_type(), 'payload': payload.decode().replace('\r\n', '\n')}
            if cd := part['Content-Disposition']:
                part_info['Content-Disposition'] = cd
            d['payload'].append(part_info)

    return {'body': dict(data), 'email': d}


async def ses_send(request):
    data = await request.post()
    request.app['emails'].append(email_dict(data))
    response_body = ses_send_response.format(message_id='123-message-id', request_id='123-request-id')
    return Response(body=response_body, content_type='text/xml')


routes = [
    web.get('/s3/', s3_root),
    web.get('/s3_demo_image_url/{image:.*}', s3_demo_image),
    web.post('/ses/', ses_send),
]
