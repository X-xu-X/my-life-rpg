"""One-click local launcher waits for API schema readiness, then runs its queue."""
import json
import sys
import time
from urllib.request import urlopen


def wait_for_api(timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with urlopen('http://127.0.0.1:8000/api/health',timeout=2) as response:
                if response.status==200 and json.load(response).get('app')=='game-of-life':return
        except (OSError,ValueError):pass
        time.sleep(1)
    raise RuntimeError('本地 API 未就绪，请先查看后端启动窗口；worker 未修改数据库。')


def main():
    from app.config import settings
    if settings.cloud:raise RuntimeError('云端继续使用独立 worker，不使用本地启动器。')
    wait_for_api()
    from app.worker import main as worker_main
    sys.argv=[sys.argv[0],'--local']
    worker_main()


if __name__=='__main__':main()
