"""从受限文件读取数据库口令，不把 DSN 写进启动命令或日志。"""
import os
import sys
from pathlib import Path
from sqlalchemy.engine import URL

if not os.environ.get('DB_URL'):
    password = Path(os.environ['DB_PASSWORD_FILE']).read_text().strip()
    if len(password) < 24:
        raise RuntimeError('数据库口令长度不足。')
    os.environ['DB_URL'] = URL.create('postgresql+psycopg', username='gol_app', password=password,
        host='db', port=5432, database='game_of_life').render_as_string(hide_password=False)
os.execvp(sys.argv[1], sys.argv[1:])
