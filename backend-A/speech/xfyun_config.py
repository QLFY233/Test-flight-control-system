"""
讯飞语音配置 — 从环境变量读取密钥。
STT: 需 XF_APP_ID, XF_API_KEY, XF_API_SECRET (hmac-sha256 签名)
TTS: 需 XF_API_PASSWORD (x-api-key 方式)
"""
import os

XF_APP_ID = os.environ.get("XF_APP_ID", "")
XF_API_KEY = os.environ.get("XF_API_KEY", "")
XF_API_SECRET = os.environ.get("XF_API_SECRET", "")
XF_API_PASSWORD = os.environ.get("XF_API_PASSWORD", "")

# STT WebSocket URL
STT_WS_URL = "wss://iat.xf-yun.com/v1"

# TTS WebSocket URL
TTS_WS_URL = "wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6"


def is_stt_configured() -> bool:
    return bool(XF_APP_ID and XF_API_KEY and XF_API_SECRET)


def is_tts_configured() -> bool:
    return bool(XF_API_PASSWORD)
