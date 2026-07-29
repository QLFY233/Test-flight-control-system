"""
ActionTranslator 统一接口 — α 动作翻译器 ABC。
α 不对话, 纯翻译: 接收指令文本 + 位姿 + 环境 → ActionCommand。
先导 LLM 实现, 远期换蒸馏小模型 α (接口不变)。
translate() 是同步方法 — α loop 通过 asyncio.to_thread 调用,
防止 LLM 调用阻塞事件循环 (总体架构 §2.3)。
"""
import json
from abc import ABC, abstractmethod


class TranslateError(Exception):
    """α 翻译失败。上层捕获后下发 hover。"""
    pass


class ActionTranslator(ABC):
    """α 动作翻译器统一接口 (总体架构 §3.7 + 开放式接口规范 §5.1)。
    同步方法, 由 α loop 通过 asyncio.to_thread 调用。
    """

    @abstractmethod
    def translate(self, intent: str, pose: dict, env: dict) -> dict:
        """输入: 指令文本 + 当前位姿 + 环境
        输出: ActionCommand dict:
          {task_id, schema_version:2, actions:[{code, value?, target?, units?}], safety_constraints}
        失败抛 TranslateError, α loop 捕获后下发 hover。
        """
        ...
