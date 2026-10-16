# LLM 统一调用封装（可插拔）

"""LLM 服务层：所有大模型调用都集中在这里，业务代码不得直接调用 openai SDK。

可插拔设计（PRD 5 节）：
- 模型名 / base_url / api_key 全部从配置（.env）读取，不写死在业务代码。
- 未来切换模型或供应商时，仅改 .env 配置，不动业务逻辑。
"""
import json
import math
import re
import time
import hashlib
import threading
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from openai import OpenAI

from app.config import settings
CALL_GUARD = ContextVar("model_call_guard", default=None)
USAGE_FACTORY = ContextVar("model_usage_factory", default=None)
_model_slot = threading.BoundedSemaphore(1)


def _release_model_slot(connection):
    try:
        if connection is not None:
            from sqlalchemy import text
            try:
                connection.execute(text('SELECT pg_advisory_unlock(61111201)'))
                connection.commit()
            except Exception:
                connection.invalidate()
            finally:
                connection.close()
    finally:
        _model_slot.release()


def reserve_usage(config):
    if not settings.cloud:
        return
    from app.database import SessionLocal
    from app.models.analysis import ModelUsage
    from app.services.time_service import clock_now
    from sqlalchemy.exc import IntegrityError
    factory = USAGE_FACTORY.get() or SessionLocal
    day = clock_now().date()
    with factory() as db:
        row = db.query(ModelUsage).filter_by(user_id=config.user_id, local_date=day).first()
        if row is None:
            try:
                with db.begin_nested():
                    db.add(ModelUsage(user_id=config.user_id, local_date=day, calls=0))
                    db.flush()
            except IntegrityError:
                pass
        changed = db.query(ModelUsage).filter(ModelUsage.user_id == config.user_id,
            ModelUsage.local_date == day, ModelUsage.calls < settings.ai_daily_limit).update(
                {ModelUsage.calls: ModelUsage.calls + 1}, synchronize_session=False)
        if changed != 1:
            db.rollback()
            raise LLMError("MODEL_DAILY_LIMIT：今日分析预算已用完，仍可继续保存文字。")
        db.commit()

if TYPE_CHECKING:  # 仅供类型标注；运行时不导入（llm_config 会导入本模块的 LLMError）
    from app.services.llm_config import LLMConfig


def _strict_json_loads(raw):
    def reject_constant(value):
        raise ValueError("模型返回非标准数值：" + value)
    value = json.loads(raw, parse_constant=reject_constant)
    def validate(v):
        if type(v) is int and not -(2**63) <= v < 2**63:
            raise ValueError("模型整数超出 SQLite 存储范围。")
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("模型数值超出有限范围。")
        if isinstance(v, dict):
            for item in v.values(): validate(item)
        elif isinstance(v, list):
            for item in v: validate(item)
    validate(value)
    if not isinstance(value, dict):
        raise ValueError("模型返回必须是 JSON 对象。")
    return value


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
        if settings.cloud:
            if config is None:
                raise LLMError("MODEL_NOT_CONFIGURED：分析前请绑定自己的模型。")
            from app.services.model_boundary import IsolatedClient
            return IsolatedClient(config)
        if config is not None:
            key = (hashlib.sha256(config.api_key.encode()).hexdigest(), config.base_url)
            client = self._clients.get(key)
            if client is None:
                if len(self._clients) >= 16:
                    self._clients.pop(next(iter(self._clients))).close()
                client = OpenAI(api_key=config.api_key, base_url=config.base_url, max_retries=0, timeout=settings.ai_timeout)
                self._clients[key] = client
            return client
        # .env 默认路径（未传 config 时，行为与 v1.3 完全一致）
        if not settings.llm_ready:
            raise LLMError(
                "尚未配置 DEEPSEEK_API_KEY。请到「设置 → AI 模型」绑定密钥，"
                "或复制 .env.example 为 .env 并填入真实密钥。"
            )
        key = (hashlib.sha256(settings.deepseek_api_key.encode()).hexdigest(), settings.deepseek_base_url)
        client = self._clients.get(key)
        if client is None:
            if len(self._clients) >= 16:
                self._clients.pop(next(iter(self._clients))).close()
            client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, max_retries=0, timeout=settings.ai_timeout)
            self._clients[key] = client
        return client

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        config: "LLMConfig | None" = None,
        max_tokens: int | None = None,
    ) -> str:
        """发起一次对话补全，返回文本内容。

        :param messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        :param temperature: 采样温度，默认取配置（判定用 0.3 保证口径稳定）
        :param json_mode: 是否要求模型输出 JSON（DeepSeek 需 prompt 含 json 关键字）
        :param config: v1.4 可选覆盖配置（BYOK）；不传走 .env 默认
        """
        if settings.cloud and not _model_slot.acquire(blocking=False):
            raise LLMError("MODEL_BUSY：分析正在进行，请稍后重试。")
        client = None
        global_lock = None
        hosted_usage_id = None
        hosted_factory = None
        try:
            if settings.cloud:
                from app.database import SessionLocal
                from sqlalchemy import text
                factory = USAGE_FACTORY.get() or SessionLocal
                with factory() as usage_db:
                    bind = usage_db.get_bind()
                if bind.dialect.name == 'postgresql':
                    global_lock = bind.connect()
                    if not global_lock.execute(text('SELECT pg_try_advisory_lock(61111201)')).scalar():
                        global_lock.close()
                        global_lock = None
                        raise LLMError("MODEL_BUSY：分析正在进行，请稍后重试。")
                    global_lock.commit()
            guard = CALL_GUARD.get()
            if guard:
                guard()
            if settings.cloud and getattr(config,'scope','personal')=='hosted':
                from app.services import hosted_ai
                hosted_factory=factory
                hosted_usage_id=hosted_ai.reserve(hosted_factory,config,messages)
            else:reserve_usage(config)
            client = self._get_client(config)
        except Exception:
            try:
                if hosted_usage_id is not None:hosted_ai.settle(hosted_factory,hosted_usage_id,error='NOT_DISPATCHED')
            finally:
                if settings.cloud:_release_model_slot(global_lock)
            raise
        temp = settings.llm_temperature if temperature is None else temperature

        kwargs: dict[str, Any] = {
            "model": config.model if config is not None else settings.deepseek_model,
            "messages": messages,
            "temperature": temp,
        }
        if getattr(config,'scope','personal')=='hosted':max_tokens=min(max_tokens or config.max_output_tokens,config.max_output_tokens)
        if max_tokens is not None:
            limit_key = 'max_completion_tokens' if config and config.base_url.rstrip('/') == 'https://api.openai.com/v1' else 'max_tokens'
            kwargs[limit_key] = max_tokens
        # 开启 JSON 输出模式，保证结构化结果稳定
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            if hosted_usage_id is not None:hosted_ai.dispatched(hosted_factory,config,hosted_usage_id)
            resp = client.chat.completions.create(**kwargs)
            if hosted_usage_id is not None and hosted_ai.settle(hosted_factory,hosted_usage_id,response=resp)=='overrun':raise LLMError('MODEL_DAILY_LIMIT：供应商报告用量超出配置上限，站点模型已停用。')
        except Exception as exc:
            from app.services.model_errors import category
            code = str(exc).split('：',1)[0] if isinstance(exc,LLMError) else category(exc)
            if hosted_usage_id is not None:hosted_ai.settle(hosted_factory,hosted_usage_id,error=code)
            raise LLMError(code + "：分析失败，原文已保存，请检查模型配置后重试。") from None
        finally:
            if settings.cloud:
                try:
                    client.close()
                finally:
                    _release_model_slot(global_lock)

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
        v1.5 A5：空 content / JSON 解析失败 / 解析结果无有效字段时自动重试 1 次
        （指数退避 ~1s），重试仍失败才抛 LLMError。重试幂等安全（重判均为就地更新）。
        """
        last_error: Exception | None = None
        for attempt in range(2):
            if attempt == 1:
                time.sleep(1.0)  # 指数退避：第 1 次重试前等待 ~1s
            raw = self.chat(messages, temperature=temperature, json_mode=True, config=config)
            if not raw or not raw.strip():
                last_error = LLMError("模型返回内容为空")
                continue
            try:
                result = self._parse_json(raw)
            except LLMError as exc:
                last_error = exc
                continue
            if not isinstance(result, dict) or not result:
                last_error = LLMError("模型返回 JSON 无有效字段")
                continue
            return result
        if settings.cloud:
            raise LLMError('MODEL_INVALID_RESPONSE：模型返回无效内容，原文已保存，请稍后重试。')
        raise LLMError(
            "AI 服务偶发抖动，已自动重试仍失败，请稍后重试。" f"（{last_error}）"
        )

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
            return _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError):
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
                return _strict_json_loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
        raise LLMError(f"LLM 返回内容无法解析为 JSON：{raw[:200]}")


# 全局单例，业务层统一 import 使用
llm_service = LLMService()
