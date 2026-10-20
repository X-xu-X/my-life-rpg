"""独立进程入口：python -m app.worker；不运行 Web lifespan 或自动迁移。"""
import signal
import time
import logging
import argparse
import tempfile
from pathlib import Path
from app.database import SessionLocal
from app.services import owned_repository
from app.services.analysis_jobs import claim, process

stopping = False


def maintain(factory):
    """到期写入由后台显式执行，页面 GET 保持只读。"""
    from app.models import User, UserProfile
    from app.services.time_service import USER_ZONE
    from app.services.challenge_service import expire_stale
    with factory() as db:
        ids = [uid for uid, in db.query(User.id).join(UserProfile, UserProfile.user_id == User.id)
               .filter(User.status == 'active', UserProfile.onboarding_completed.is_(True)).order_by(User.id)]
    for uid in ids:
        with factory() as db:
            user = db.get(User, uid)
            db.info['user_id'] = uid
            zone_token = USER_ZONE.set(user.timezone)
            try:
                expire_stale(db, user)
            except Exception as exc:
                db.rollback()
                logging.getLogger(__name__).warning('challenge maintenance failed: %s', type(exc).__name__)
            finally:
                USER_ZONE.reset(zone_token)


def stop(signum, frame):
    global stopping
    stopping = True


def validate_local_schema(bind):
    """Read-only: API startup owns backup/schema updates for local files."""
    from sqlalchemy import inspect
    from app.database import Base
    inspector=inspect(bind)
    tables=set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in tables or not set(table.columns.keys()).issubset({column['name'] for column in inspector.get_columns(table.name)}):
            raise RuntimeError('本地数据库结构未就绪；请先启动 API 完成备份和结构升级，再启动 worker --local。')


def main():
    from app.main import init_db
    from app.config import settings
    parser=argparse.ArgumentParser()
    parser.add_argument('--local',action='store_true',help='显式运行单实例本地队列；不建表或迁移')
    args=parser.parse_args()
    if settings.cloud:
        if args.local:raise RuntimeError('cloud 部署使用原 worker 命令，不接受 --local。')
        init_db()  # cloud 路径只检查配置与迁移版本。
        heartbeat=Path('/tmp/gol-worker-heartbeat')
    else:
        if not args.local:raise RuntimeError('本地队列需显式运行 python -m app.worker --local。')
        from app.database import engine
        validate_local_schema(engine)
        heartbeat=Path(tempfile.gettempdir())/'gol-local-worker-heartbeat'
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    next_maintenance = 0.0
    while not stopping:
        heartbeat.touch()
        from app.services.mail_queue import deliver_one
        try:
            deliver_one(SessionLocal)
        except Exception as exc:
            logging.getLogger(__name__).warning('mail worker failed: %s',type(exc).__name__)
        if time.monotonic() >= next_maintenance:
            maintain(SessionLocal)
            next_maintenance = time.monotonic() + 60
        job = claim(SessionLocal)
        if job:
            process(SessionLocal, job)
        else:
            time.sleep(1)


if __name__ == "__main__": main()
