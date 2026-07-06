"""讯飞 STT authentication — HMAC-SHA256 signature builder."""

import base64
import hashlib
import hmac
import time
from email.utils import formatdate
from urllib.parse import urlencode

from backend_A.speech.xfyun_config import XF_API_KEY, XF_API_SECRET


def build_auth_url(host: str, path: str = "/v1") -> str:
    """Build the authenticated WebSocket URL for 讯飞 STT.

    Args:
        host: e.g. "iat.xf-yun.com"
        path: e.g. "/v1"

    Returns:
        Authenticated URL string with authorization parameters.
    """
    # RFC 1123 date
    now = formatdate(timeval=time.time(), localtime=False, usegmt=True)

    # Signature origin
    signature_origin = f"host: {host}\ndate: {now}\nGET {path} HTTP/1.1"

    # HMAC-SHA256
    signature_sha = hmac.new(
        XF_API_SECRET.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature_b64 = base64.b64encode(signature_sha).decode("utf-8")

    # Authorization header value
    authorization_origin = (
        f'api_key="{XF_API_KEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature_b64}"'
    )
    authorization_b64 = base64.b64encode(
        authorization_origin.encode("utf-8")
    ).decode("utf-8")

    # Build query parameters
    params = {
        "authorization": authorization_b64,
        "date": now,
        "host": host,
    }
    query_string = urlencode(params)

    return f"wss://{host}{path}?{query_string}"
