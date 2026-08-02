"""
讯飞 TTS 客户端 — WebSocket 连接, 发送文本, 接收 base64 MP3 音频。
鉴权方式: x-api-key (方式一)。
"""
import json
import logging
from .xfyun_config import TTS_WS_URL, XF_APP_ID, XF_API_PASSWORD, is_tts_configured

logger = logging.getLogger(__name__)


class TtsClient:
    """讯飞语音合成客户端 (TTS)。

    用法:
        client = TtsClient()
        mp3_data = await client.synthesize("你好世界")
    """

    def __init__(self):
        self._ws = None

    def is_available(self) -> bool:
        return is_tts_configured()

    async def synthesize(self, text: str) -> bytes:
        """合成语音, 返回 MP3 字节 (base64 解码后)。"""
        if not is_tts_configured():
            raise RuntimeError("TTS not configured — set XF_API_PASSWORD")

        # 构建鉴权 URL (x-api-key 方式)
        import base64 as b64  # N11: 移除未使用的 time/hashlib import

        # TTS 使用 x-api-key 鉴权, 签名参数附加到 URL
        try:
            import websockets

            # 拼接带鉴权的 URL
            auth_url = TTS_WS_URL

            self._ws = await websockets.connect(
                auth_url,
                extra_headers={
                    "X-Api-Key": XF_API_PASSWORD,
                },
            )
            logger.info("[tts] connected to iFlytek TTS")
        except ImportError:
            raise RuntimeError("websockets package not installed")
        except Exception as e:
            logger.error(f"[tts] connect failed: {e}")
            raise

        # 发送合成参数
        params = {
            "common": {"app_id": XF_APP_ID},
            "business": {
                "aue": "lame",   # MP3 格式
                "sfl": 1,         # 流式返回
                "auf": "audio/L16;rate=24000",
                "vcn": "xiaoyan",  # 发音人
                "speed": 50,
                "volume": 50,
                "pitch": 50,
                "tte": "utf8",
            },
            "data": {
                "status": 2,      # 2=一次性合成
                "text": b64.b64encode(text.encode("utf-8")).decode("utf-8"),
            },
        }
        await self._ws.send(json.dumps(params))

        # 接收音频数据
        mp3_chunks = []
        try:
            async for msg in self._ws:
                resp = json.loads(msg)
                if resp.get("code") != 0:
                    logger.warning(f"[tts] error: {resp}")
                    break
                data = resp.get("data", {})
                audio_b64 = data.get("audio", "")
                if audio_b64:
                    mp3_chunks.append(b64.b64decode(audio_b64))
                if data.get("status") == 2:
                    break
        except Exception as e:
            logger.error(f"[tts] receive error: {e}")
        finally:
            await self._ws.close()

        mp3_data = b"".join(mp3_chunks)
        logger.info(f"[tts] synthesized: {len(mp3_data)} bytes MP3 for '{text[:30]}...'")
        return mp3_data
