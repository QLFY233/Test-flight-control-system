"""
讯飞 STT 签名 — hmac-sha256 签名, 构建鉴权 URL。
规范: RFC1123 UTC date, ±300s 允许偏差。
"""
import hmac
import hashlib
import base64
import time
from urllib.parse import urlencode, quote


def build_auth_url(host: str, api_key: str, api_secret: str) -> str:
    """构建讯飞 STT WebSocket 鉴权 URL。

    返回: wss://host/v1?authorization=...&date=...&host=...
    """
    # RFC1123 UTC date
    now = time.time()
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(now))

    # 签名字符串: host + date + HTTP方法
    signature_origin = f"host: {host}\ndate: {date}\nGET /v1 HTTP/1.1"

    # hmac-sha256 签名 → base64
    signature = base64.b64encode(
        hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    # 构造 authorization
    authorization = base64.b64encode(
        f"api_key=\"{api_key}\", algorithm=\"hmac-sha256\", headers=\"host date request-line\", signature=\"{signature}\"".encode(
            "utf-8"
        )
    ).decode("utf-8")

    # URL 编码
    params = {
        "authorization": authorization,
        "date": date,
        "host": host,
    }

    return f"wss://{host}/v1?{urlencode(params)}"
