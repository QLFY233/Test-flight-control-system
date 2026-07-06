"""讯飞 (iFlytek) configuration — read from environment variables.

Keys are never stored in config files or committed to git.
"""

import os
import logging

logger = logging.getLogger(__name__)

# STT (语音听写) credentials
XF_APP_ID = os.environ.get("XF_APP_ID", "")
XF_API_KEY = os.environ.get("XF_API_KEY", "")
XF_API_SECRET = os.environ.get("XF_API_SECRET", "")

# TTS (语音合成) credentials
XF_API_PASSWORD = os.environ.get("XF_API_PASSWORD", "")

# STT WebSocket URL
XF_STT_URL = "wss://iat.xf-yun.com/v1"

# TTS WebSocket URL
XF_TTS_URL = "wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6"

# Default TTS voice
XF_TTS_VCN = os.environ.get("XF_TTS_VCN", "x6_lingxiaoxuan_flow")


def is_configured() -> bool:
    """Check if 讯飞 credentials are configured."""
    return bool(XF_APP_ID and XF_API_KEY and XF_API_SECRET)


def is_tts_configured() -> bool:
    """Check if TTS credentials are configured."""
    return bool(XF_API_PASSWORD)
