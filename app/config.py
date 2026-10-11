"""全局配置。

所有可配置项统一从环境变量（.env）读取，严禁在代码中硬编码密钥。
模型名 / base_url 可插拔：未来切换模型或供应商时仅需修改 .env，不动业务代码。
"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（app/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置。字段名与环境变量名一一对应（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- DeepSeek / LLM 配置（可插拔）----
    deepseek_api_key: str = ""  # 真实密钥仅从 .env 读取，默认空避免误提交
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 判定要求口径稳定、低随机。v1.5 B2：0.3→0.2（实测 0.3 维度/加点漂移明显，
    # 0=完全确定但措辞呆板，0.2 为平衡点；如需微调只改此处）
    llm_temperature: float = 0.2

    # ---- 数据库 ----
    # V1 使用 SQLite；表结构已预留 MySQL/PostgreSQL 平滑迁移（见 models/models.py）
    db_file: str = "game_of_life.db"
    # 预留：未来上云时可改为 MySQL 连接串，例如
    # db_url: str = "mysql+pymysql://user:pass@host:3306/game_of_life"
    db_url: str = ""  # 若显式指定则优先使用，否则根据 db_file 拼 SQLite URL
    run_mode: Literal['local', 'cloud'] = "local"  # 配置拼写错误必须启动失败。
    public_origin: str = ""
    credential_key_file: str = ""
    allow_cloud_sqlite: bool = False
    ai_daily_limit: int = 30
    ai_timeout: float = 90.0

    @property
    def cloud(self) -> bool:
        return self.run_mode == "cloud"

    @property
    def database_url(self) -> str:
        """返回 SQLAlchemy 连接串。

        优先使用显式 db_url（预留 MySQL/PostgreSQL）；否则回退到本地 SQLite 文件。
        """
        if self.db_url:
            return self.db_url
        return f"sqlite:///{BASE_DIR / self.db_file}"

    @property
    def llm_ready(self) -> bool:
        """LLM 是否可用（已配置密钥）。用于无密钥时给出友好提示。"""
        return bool(self.deepseek_api_key and self.deepseek_api_key.startswith("sk-"))


settings = Settings()
