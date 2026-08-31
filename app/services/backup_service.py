"""自动备份服务：SQLite 本地备份（个人数据主权保障）。

- 启动时自动备份 + 设置页可手动备份
- 用 SQLite backup API（在线安全复制，不锁库）
- 保留最近 N 份，更旧的自动清理
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, settings

BACKUP_DIR = BASE_DIR / "backups"
BACKUP_KEEP = 30  # 保留最近 30 份备份


def backup_now() -> Path | None:
    """备份当前数据库到 backups/。返回备份文件路径（失败返回 None）。"""
    db_path = Path(BASE_DIR / settings.db_file)
    if not db_path.exists():
        return None
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"game_of_life_{ts}.db"
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    except Exception:
        # 备份失败不影响主流程，静默返回 None
        dest.unlink(missing_ok=True)
        return None
    _cleanup()
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
    """保留最近 BACKUP_KEEP 份，删除更旧的。"""
    files = sorted(BACKUP_DIR.glob("game_of_life_*.db"))
    for f in files[:-BACKUP_KEEP] if len(files) > BACKUP_KEEP else []:
        f.unlink(missing_ok=True)
