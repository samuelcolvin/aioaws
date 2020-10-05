import base64
from email import message_from_bytes
from email.header import decode_header
from typing import Any, Dict
from uuid import uuid4

__all__ = 'ses_email_data', 'ses_send_response'


def ses_email_data(data: Dict[str, str]) -> Dict[str, Any]:
    """
    Convert raw email body data to a useful representation of an email for testing.
    """
    msg_raw = base64.b64decode(data['RawMessage.Data'])
    msg = message_from_bytes(msg_raw)
    d: Dict[str, Any] = {}
    for k, v in msg.items():
        if k != 'Content-Type':
            value = decode_header(v)[0][0]
            if isinstance(value, bytes):
                d[k] = value.decode()
            else:
                d[k] = value

    d['payload'] = []
    for part in msg.walk():
        if payload := part.get_payload(decode=True):
            part_info = {'Content-Type': part.get_content_type(), 'payload': payload.decode().replace('\r\n', '\n')}
            if cd := part['Content-Disposition']:
                part_info['Content-Disposition'] = cd
            d['payload'].append(part_info)

    return {'body': dict(data), 'email': d}


def ses_send_response(message_id: str = None, request_id: str = None) -> str:
    """
    Dummy response to SendRawEmail SES endpoint
    """
    return (
        f'<SendRawEmailResponse xmlns="http://ses.amazonaws.com/doc/2010-12-01/">\n'
        f'  <SendRawEmailResult>\n'
        f'    <MessageId>{message_id or uuid4()}</MessageId>\n'
        f'  </SendRawEmailResult>\n'
        f'  <ResponseMetadata>\n'
        f'    <RequestId>{request_id or uuid4()}</RequestId>\n'
        f'  </ResponseMetadata>\n'
        f'</SendRawEmailResponse>\n'
    )
