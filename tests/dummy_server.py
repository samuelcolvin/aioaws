from io import BytesIO

from aiohttp import web
from aiohttp.web_response import Response
from PIL import Image, ImageDraw

from aioaws.testing import ses_email_data, ses_send_response

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


async def ses_send(request):
    data = await request.post()
    request.app['emails'].append(ses_email_data(data))
    return Response(body=ses_send_response('123-message-id', '123-request-id'), content_type='text/xml')


aws_certs_body = (
    '-----BEGIN CERTIFICATE-----\n'
    'MIIFbDCCBFSgAwIBAgIQB3iuJ5ay6FT2RU7MQY+1HTANBgkqhkiG9w0BAQsFADBG\n'
    'MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRUwEwYDVQQLEwxTZXJ2ZXIg\n'
    'Q0EgMUIxDzANBgNVBAMTBkFtYXpvbjAeFw0yMDAxMDYwMDAwMDBaFw0yMDEyMTUx\n'
    'MjAwMDBaMBwxGjAYBgNVBAMTEXNucy5hbWF6b25hd3MuY29tMIIBIjANBgkqhkiG\n'
    '9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtYPg4ZvdkGmoJk87x25mt+H8/u5zbhcp8gDr\n'
    'rmRQCqCeDg8cFJQrHK3GJ4q3ZmfmYx0R4bB9NuMgBm6EVc5Or9aEO7uO6Ceakswc\n'
    'AeW7yh6HlVQVM+z43tm2oA6kNUtYhR6tVOkOCUYLVENyMj6robGqpbRNGB2O2dHm\n'
    'RChEcw7s917S7aDE/KK8Sr2rj4sPTIx1Et4YmQzuxkyQiIWGn4heZimPcmjxUoaW\n'
    'PdiQEAXP9tGDNhh7HXsZUbXVEd4jId6teQ7apIZu5DAtfR3iWtODiHUQDdRHocGn\n'
    'JGSAaNULy42NEacBmPZDD9hSwTT7AjvLV9OT5/h3sMOgWUyXuwIDAQABo4ICfjCC\n'
    'AnowHwYDVR0jBBgwFoAUWaRmBlKge5WSPKOUByeWdFv5PdAwHQYDVR0OBBYEFMdf\n'
    'G1DiGbwTh2rj61Jc0aLPQgm1MBwGA1UdEQQVMBOCEXNucy5hbWF6b25hd3MuY29t\n'
    'MA4GA1UdDwEB/wQEAwIFoDAdBgNVHSUEFjAUBggrBgEFBQcDAQYIKwYBBQUHAwIw\n'
    'OwYDVR0fBDQwMjAwoC6gLIYqaHR0cDovL2NybC5zY2ExYi5hbWF6b250cnVzdC5j\n'
    'b20vc2NhMWIuY3JsMCAGA1UdIAQZMBcwCwYJYIZIAYb9bAECMAgGBmeBDAECATB1\n'
    'BggrBgEFBQcBAQRpMGcwLQYIKwYBBQUHMAGGIWh0dHA6Ly9vY3NwLnNjYTFiLmFt\n'
    'YXpvbnRydXN0LmNvbTA2BggrBgEFBQcwAoYqaHR0cDovL2NydC5zY2ExYi5hbWF6\n'
    'b250cnVzdC5jb20vc2NhMWIuY3J0MAwGA1UdEwEB/wQCMAAwggEFBgorBgEEAdZ5\n'
    'AgQCBIH2BIHzAPEAdwDuS723dc5guuFCaR+r4Z5mow9+X7By2IMAxHuJeqj9ywAA\n'
    'AW98PqF0AAAEAwBIMEYCIQD95G28wQGco+wtlUGyEhEnayn9+D/4JaQ0wWGnE5aZ\n'
    'owIhAJ2xRJBhTfEaumwb2gYV60wbKqJBLv2S4lB2XKlIzmClAHYAh3W/51l8+IxD\n'
    'mV+9827/Vo1HVjb/SrVgwbTq/16ggw8AAAFvfD6h9QAABAMARzBFAiEArgO+z3xy\n'
    'VterBTmDl/ntcsn6nTfY/QDAAxg8w4r1XysCIHh6SHMltWgzoFi97d4RqsF9HJir\n'
    '0YTk902CnTy46D/YMA0GCSqGSIb3DQEBCwUAA4IBAQAT16YuGrKpiMg4Wj7yPSi5\n'
    'ExdXE2TR1gTNFYbIYkjKqdIbWGckQnYoWdT/XV8r6ejoW+cwKRF7+dOhPOWm41ZB\n'
    'WZs3vumBwTkLEK2qelTPwhsNT8IhZkz1KO39Ha05nYg93hn/3Xdj9zJhIpJlSdWE\n'
    'B6AKxrwd40p7iVbBfQlff+16WjVgzIvmkybS2wkjV6Mry7/UqOEv1jWsPB24uflz\n'
    'fbyFqmw5O2ahvjIaaM9uMZhDnlLaUu9aj2Nvmfv7mywIzPA7ONlaQ7Pb5PqqZytH\n'
    'A2vZSDQAXkx38hiGrQLwAO3ymWsnQ9isf5MCCuLAnFC1ubIWqZYAWAzDa8SY36B/\n'
    '-----END CERTIFICATE-----\n'
)


async def aws_certs(request):
    return Response(body=aws_certs_body, content_type='content/unknown')


routes = [
    web.get('/s3/', s3_root),
    web.get('/s3_demo_image_url/{image:.*}', s3_demo_image),
    web.post('/ses/', ses_send),
    web.get('/sns/certs/', aws_certs),
]
