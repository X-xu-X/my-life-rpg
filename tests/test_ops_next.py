"""迁移与预检仅操作合成副本。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from app.config import settings
from app.database import Base
from app import models as m
import app.models.access, app.models.analysis

spec=importlib.util.spec_from_file_location('sqlite_importer',Path('ops/import-sqlite.py'))
importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)


class OpsTests(unittest.TestCase):
    def test_frozen_migrations_empty_sqlite_and_repeat(self):
        with tempfile.TemporaryDirectory(dir='backups',prefix='migration_test_') as temp:
            url='sqlite:///'+str(Path(temp)/'synthetic.sqlite3')
            config=Config('alembic.ini');config.attributes['database_url']=url
            command.upgrade(config,'head');command.upgrade(config,'head')
            engine=create_engine(url)
            with engine.connect() as db:
                self.assertEqual(db.execute(text('SELECT version_num FROM alembic_version')).scalar(),'b008_accounts')
                self.assertEqual(db.execute(text('SELECT count(*) FROM users')).scalar(),0)
            engine.dispose()

    def test_preflight_preserves_dangling_judgment_35_event_34(self):
        with tempfile.TemporaryDirectory(dir='backups',prefix='import_test_') as temp,patch.object(settings,'run_mode','local'):
            source=Path(temp)/'synthetic.sqlite3'
            engine=create_engine('sqlite:///'+str(source))
            Base.metadata.create_all(engine,tables=[Base.metadata.tables[name] for name in importer.TABLES])
            with Session(engine) as db:
                user=m.User(username='default');db.add(user);db.flush()
                db.add(m.UserProfile(user_id=user.id,coins=40,onboarding_completed=True))
                db.add(m.AIJudgment(id=35,user_id=user.id,event_id=34,status='pending',confidence=1))
                db.commit()
            engine.dispose()
            before=source.read_bytes()
            data,report=importer.preflight(source)
            self.assertTrue(report['blocked'])
            self.assertTrue(any(issue.get('table')=='ai_judgments' and issue.get('id')==35
                and issue.get('referenced_id')==34 for issue in report['issues']))
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(data['user_profiles'][0]['coins'],40)


if __name__=='__main__':unittest.main()
