"""
讯飞 STT 客户端 — WebSocket 连接, 发送 PCM 音频, 接收识别结果。
支持 wpgs (动态修正) 中间结果。
"""
import json
import logging
from .xfyun_config import (
    STT_WS_URL, XF_APP_ID, XF_API_KEY, XF_API_SECRET, is_stt_configured,
)
from .auth import build_auth_url

logger = logging.getLogger(__name__)


class SttClient:
    """讯飞语音识别客户端 (STT)。

    用法:
        client = SttClient()
        await client.connect()
        await client.send_audio(pcm_bytes)  # 16k/16bit/mono PCM
        result = await client.finish()
    """

    def __init__(self):
        self._ws = None
        self._results: list[str] = []

    def is_available(self) -> bool:
        return is_stt_configured()

    async def connect(self):
        """建立 WebSocket 连接并发送开始帧。"""
        if not is_stt_configured():
            raise RuntimeError("STT not configured — set XF_APP_ID/XF_API_KEY/XF_API_SECRET")

        # 从 URL 提取 host
        host = STT_WS_URL.replace("wss://", "").replace("/v1", "")
        url = build_auth_url(host, XF_API_KEY, XF_API_SECRET)

        try:
            import websockets
            self._ws = await websockets.connect(url)
            logger.info("[stt] connected to iFlytek STT")
        except ImportError:
            raise RuntimeError("websockets package not installed")
        except Exception as e:
            logger.error(f"[stt] connect failed: {e}")
            raise

        # 发送开始参数帧
        params = {
            "common": {"app_id": XF_APP_ID},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "dwa": "wpgs",  # 动态修正
            },
            "data": {
                "status": 0,  # 0=开始
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            },
        }
        await self._ws.send(json.dumps(params))

    async def send_audio(self, pcm_data: bytes):
        """发送 PCM 音频数据 (16k/16bit/mono)。"""
        if not self._ws:
            raise RuntimeError("Not connected")
        frame = {
            "data": {
                "status": 1,  # 1=继续
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": base64_encode(pcm_data),
            }
        }
        await self._ws.send(json.dumps(frame))

    async def finish(self) -> str:
        """发送结束帧, 接收最终识别结果。"""
        if not self._ws:
            return ""

        # 结束帧
        end_frame = {
            "data": {
                "status": 2,  # 2=结束
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            }
        }
        await self._ws.send(json.dumps(end_frame))

        # 接收结果
        full_text = []
        try:
            async for msg in self._ws:
                resp = json.loads(msg)
                if resp.get("code") != 0:
                    logger.warning(f"[stt] error: {resp}")
                    break
                data = resp.get("data", {})
                result = data.get("result", {})
                # ws 字段含动态修正结果
                ws = result.get("ws", [])
                for w in ws:
                    cw = w.get("cw", [])
                    for c in cw:
                        word = c.get("w", "")
                        if word:
                            full_text.append(word)
                # 检查是否结束
                if data.get("status") == 2:
                    break
        except Exception as e:
            logger.error(f"[stt] receive error: {e}")
        finally:
            await self._ws.close()

        text = "".join(full_text)
        logger.info(f"[stt] recognized: {text[:100]}")
        return text


def base64_encode(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("utf-8")
