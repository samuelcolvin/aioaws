from io import BytesIO

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


routes = [
    web.get('/s3/', s3_root),
    web.get('/s3_demo_image_url/{image:.*}', s3_demo_image),
]
