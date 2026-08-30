# LLM 统一调用封装（可插拔）

"""LLM 服务层：所有大模型调用都集中在这里，业务代码不得直接调用 openai SDK。

可插拔设计（PRD 5 节）：
- 模型名 / base_url / api_key 全部从配置（.env）读取，不写死在业务代码。
- 未来切换模型或供应商时，仅改 .env 配置，不动业务逻辑。
"""
import json
import re
from typing import Any

from openai import OpenAI

from app.config import settings


class LLMError(RuntimeError):
    """LLM 调用或解析失败的统一异常。"""


class LLMService:
    """DeepSeek（OpenAI 兼容）调用的统一入口。"""

    def __init__(self) -> None:
        # 惰性初始化客户端：仅当配置了密钥时才创建，避免误用
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """获取（或懒创建）OpenAI 兼容客户端。"""
        if self._client is None:
            if not settings.llm_ready:
                raise LLMError(
                    "尚未配置 DEEPSEEK_API_KEY。请复制 .env.example 为 .env 并填入真实密钥。"
                )
            self._client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> str:
        """发起一次对话补全，返回文本内容。

        :param messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        :param temperature: 采样温度，默认取配置（判定用 0.3 保证口径稳定）
        :param json_mode: 是否要求模型输出 JSON（DeepSeek 需 prompt 含 json 关键字）
        """
        client = self._get_client()
        temp = settings.llm_temperature if temperature is None else temperature

        kwargs: dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": temp,
        }
        # 开启 JSON 输出模式，保证结构化结果稳定
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:  # 网络异常 / 鉴权失败 / 余额不足等
            raise LLMError(f"LLM 调用失败：{exc}") from exc

        content = resp.choices[0].message.content or ""
        return content

    def chat_json(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> dict:
        """发起对话并解析为 JSON 对象。

        对模型输出做容错：先尝试整体 json.loads，失败则提取首个 {...} 块再解析。
        """
        raw = self.chat(messages, temperature=temperature, json_mode=True)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """容错解析模型返回的 JSON（模型可能输出多余说明或 markdown 代码块）。"""
        text = raw.strip()
        # 去掉可能的 markdown 代码块围栏
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 提取首个平衡的大括号块
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError as exc:
                    raise LLMError(f"LLM 返回内容无法解析为 JSON：{raw[:200]}") from exc
            raise LLMError(f"LLM 返回内容不含 JSON 对象：{raw[:200]}")


# 全局单例，业务层统一 import 使用
llm_service = LLMService()
