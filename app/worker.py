"""独立进程入口：python -m app.worker；不运行 Web lifespan 或自动迁移。"""
import signal
import time
import logging
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


def main():
    from app.main import init_db
    from app.config import settings
    if not settings.cloud:
        raise RuntimeError("worker 仅在显式迁移的 cloud 模式使用。")
    init_db()  # cloud 路径只检查配置与迁移版本。
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    next_maintenance = 0.0
    while not stopping:
        Path('/tmp/gol-worker-heartbeat').touch()
        if time.monotonic() >= next_maintenance:
            maintain(SessionLocal)
            next_maintenance = time.monotonic() + 60
        job = claim(SessionLocal)
        if job:
            process(SessionLocal, job)
        else:
            time.sleep(1)


if __name__ == "__main__": main()
