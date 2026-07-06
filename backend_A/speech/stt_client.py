"""讯飞 STT WebSocket client.

For the initial phase, this is a stub that returns a placeholder message.
Full implementation connects to wss://iat.xf-yun.com/v1 with HMAC-SHA256 auth.
"""

import logging

logger = logging.getLogger(__name__)

# State tracking for streaming STT
_current_transcript: list[str] = []
_is_streaming: bool = False


async def process_voice_frame(data: str, seq: int, app_state=None) -> dict | None:
    """Process a voice frame from the frontend.

    Args:
        data: Base64-encoded PCM audio data.
        seq: Frame sequence number.
        app_state: AppState reference.

    Returns:
        dict with "text" and "is_final" keys, or None if no result yet.
    """
    global _current_transcript, _is_streaming

    from backend_A.speech.xfyun_config import is_configured

    if not is_configured():
        # Stub mode: return placeholder
        if seq == 0:
            _current_transcript = []
            _is_streaming = True

        # Simulate: return full result on seq 10+
        if seq > 10:
            _is_streaming = False
            result = {"text": "语音识别暂未配置", "is_final": True}
            _current_transcript = []
            return result

        # Intermediate: partial result
        partial = "语音识别暂未配置"[: min(seq + 1, 8)]
        return {"text": partial, "is_final": False}

    # TODO: Full implementation with WebSocket to 讯飞 STT
    logger.info(f"STT: received frame seq={seq}, data_len={len(data)}")
    return None


async def reset_stt() -> None:
    """Reset STT streaming state."""
    global _current_transcript, _is_streaming
    _current_transcript = []
    _is_streaming = False
