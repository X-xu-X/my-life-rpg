# LLM 统一调用封装（可插拔）

"""LLM 服务层：所有大模型调用都集中在这里，业务代码不得直接调用 openai SDK。

可插拔设计（PRD 5 节）：
- 模型名 / base_url / api_key 全部从配置（.env）读取，不写死在业务代码。
- 未来切换模型或供应商时，仅改 .env 配置，不动业务逻辑。
"""
import json
import re
from typing import TYPE_CHECKING, Any

from openai import OpenAI

from app.config import settings

if TYPE_CHECKING:  # 仅供类型标注；运行时不导入（llm_config 会导入本模块的 LLMError）
    from app.services.llm_config import LLMConfig


class LLMError(RuntimeError):
    """LLM 调用或解析失败的统一异常。"""


class LLMService:
    """DeepSeek（OpenAI 兼容）调用的统一入口。

    v1.4：支持按次传入 LLMConfig（BYOK 双模型架构）覆盖 .env 默认配置；
    客户端按 (api_key, base_url) 缓存复用，避免每次新建连接。
    """

    def __init__(self) -> None:
        # 客户端缓存：key=(api_key, base_url)
        self._clients: dict[tuple[str, str], OpenAI] = {}

    def _get_client(self, config: "LLMConfig | None" = None) -> OpenAI:
        """获取（或懒创建）OpenAI 兼容客户端。"""
        if config is not None:
            key = (config.api_key, config.base_url)
            client = self._clients.get(key)
            if client is None:
                client = OpenAI(api_key=config.api_key, base_url=config.base_url)
                self._clients[key] = client
            return client
        # .env 默认路径（未传 config 时，行为与 v1.3 完全一致）
        if not settings.llm_ready:
            raise LLMError(
                "尚未配置 DEEPSEEK_API_KEY。请到「设置 → AI 模型」绑定密钥，"
                "或复制 .env.example 为 .env 并填入真实密钥。"
            )
        key = (settings.deepseek_api_key, settings.deepseek_base_url)
        client = self._clients.get(key)
        if client is None:
            client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
            self._clients[key] = client
        return client

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        config: "LLMConfig | None" = None,
    ) -> str:
        """发起一次对话补全，返回文本内容。

        :param messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        :param temperature: 采样温度，默认取配置（判定用 0.3 保证口径稳定）
        :param json_mode: 是否要求模型输出 JSON（DeepSeek 需 prompt 含 json 关键字）
        :param config: v1.4 可选覆盖配置（BYOK）；不传走 .env 默认
        """
        client = self._get_client(config)
        temp = settings.llm_temperature if temperature is None else temperature

        kwargs: dict[str, Any] = {
            "model": config.model if config is not None else settings.deepseek_model,
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

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        config: "LLMConfig | None" = None,
    ) -> dict:
        """发起对话并解析为 JSON 对象。

        对模型输出做容错：先尝试整体 json.loads，失败则提取首个 {...} 块再解析。
        """
        raw = self.chat(messages, temperature=temperature, json_mode=True, config=config)
        return self._parse_json(raw)

    @staticmethod
    def _repair_curly_quotes(text: str) -> str:
        """位置感知修复模型误用的中文全角引号（v1.3 兜底）。

        规则：处于 JSON 结构位置的全角引号（开引号前是 { [ , : ；闭引号后是 } ] , :，
        含对应全角字符），还原为半角定界符；其余（字符串内容里的引用）替换为「」，
        避免破坏字符串。
        """
        out: list[str] = []
        n = len(text)
        for i, ch in enumerate(text):
            if ch in "“”":
                j = i - 1
                while j >= 0 and text[j] in " \t\r\n":
                    j -= 1
                prev = text[j] if j >= 0 else ""
                k = i + 1
                while k < n and text[k] in " \t\r\n":
                    k += 1
                nxt = text[k] if k < n else ""
                if ch == "“" and prev in "{[,:，":
                    out.append('"')
                elif ch == "”" and nxt in "]},:，":
                    out.append('"')
                else:
                    out.append("「" if ch == "“" else "」")
            else:
                out.append(ch)
        fixed = "".join(out)
        # 后处理：两个定界符之间的全角逗号（"，"）是结构性分隔符，转半角
        fixed = re.sub(r'"\s*，\s*"', '","', fixed)
        return fixed

    @classmethod
    def _parse_json(cls, raw: str) -> dict:
        """容错解析模型返回的 JSON（模型可能输出多余说明或 markdown 代码块）。

        v1.3 兜底：模型偶尔用中文全角引号（“”）充当 JSON 定界符导致解析失败，
        此时做位置感知修复后再解析；仍失败才抛 LLMError。
        """
        text = raw.strip()
        # 去掉可能的 markdown 代码块围栏
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 提取首个平衡的大括号块
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        candidates = []
        if match:
            candidates.append(match.group(0))
        # 全角引号兜底（v1.3）
        if "“" in text or "”" in text:
            candidates.append(cls._repair_curly_quotes(text))
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise LLMError(f"LLM 返回内容无法解析为 JSON：{raw[:200]}")


# 全局单例，业务层统一 import 使用
llm_service = LLMService()
