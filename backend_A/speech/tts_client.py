"""讯飞 TTS WebSocket client.

For the initial phase, this is a stub that logs the request.
Full implementation connects to 讯飞 TTS service with x-api-key auth.
"""

import logging

logger = logging.getLogger(__name__)


async def synthesize(text: str) -> str | None:
    """Synthesize speech from text.

    Args:
        text: Text to synthesize.

    Returns:
        Base64-encoded mp3 audio data, or None.
    """
    from backend_A.speech.xfyun_config import is_tts_configured

    if not is_tts_configured():
        logger.info(f"TTS: not configured, would synthesize: {text[:50]}...")
        return None

    # TODO: Full implementation with WebSocket to 讯飞 TTS
    logger.info(f"TTS: synthesizing {len(text)} chars")
    return None
