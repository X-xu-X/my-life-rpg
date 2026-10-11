"""自动备份服务：SQLite 本地备份（个人数据主权保障）。

- 启动时自动备份 + 设置页可手动备份
- 用 SQLite backup API（在线安全复制，不锁库）
- 保留最近 N 份，更旧的自动清理
"""
from app.services.time_service import clock_now
import sqlite3
from contextlib import closing
from uuid import uuid4
from app.database import engine
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, settings

BACKUP_DIR = BASE_DIR / "backups"
BACKUP_KEEP = 30  # 保留最近 30 份备份


def backup_now() -> Path | None:
    """按实际引擎路径在线备份；失败不阻断启动。"""
    dest = None
    try:
        database = engine.url.database
        if engine.dialect.name != "sqlite" or not database or database == ":memory:":
            return None
        db_path = Path(database).resolve()
        if not db_path.is_file():
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = clock_now().strftime("%Y%m%d_%H%M%S_%f")
        dest = BACKUP_DIR / f"game_of_life_{stamp}_{uuid4().hex[:8]}.db"
        with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(str(dest))) as dst:
                src.backup(dst)
    except Exception:
        if dest is not None:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
        return None
    try:
        _cleanup()
    except OSError:
        pass
    return dest


def list_backups() -> list[dict]:
    """列出已有备份（按时间倒序）。"""
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("game_of_life_*.db"), reverse=True)
    return [
        {
            "file": f.name,
            "size": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for f in files
    ]


def _cleanup() -> None:
    """保留最近 BACKUP_KEEP 份，删除更旧的（删除失败静默，不影响启动）。"""
    files = sorted(BACKUP_DIR.glob("game_of_life_*.db"))
    for f in files[:-BACKUP_KEEP] if len(files) > BACKUP_KEEP else []:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass  # 删除失败（如文件占用/权限）不影响主流程
