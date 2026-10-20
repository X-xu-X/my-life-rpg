"""V1.11 显式 SQLite 副本预检及原子导入；默认只读 dry-run。

真实源库导入须另获用户授权。悬空引用阻断，不修复、不隔离、不丢行。
"""
import argparse
import hashlib
import json
import math
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import Boolean, Float, JSON, Integer, create_engine, select, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from app.database import Base
from app import models
import app.models.access, app.models.analysis
from app.time_types import DateTime
from app.services.time_service import stored_time
from ops.import_references import audit, transform, LEDGER

TABLES=('users','user_profiles','attributes','attribute_history','checkin_items','events','ai_judgments',
    'judgment_logs','goals','anchors','settings','coin_ledger','challenges','shop_items','redemptions','achievements','exemptions')
MAPPERS={mapper.local_table.name:mapper.class_ for mapper in Base.registry.mappers}


def preflight(source):
    source=Path(source).resolve(strict=True)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    issues=[];data={};summary={}
    if Path(str(source)+'-wal').exists() and Path(str(source)+'-wal').stat().st_size:
        issues.append({'reason':'SOURCE_WAL_PRESENT','action':'停源写入后获取一致副本；不自动 checkpoint'})
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': issues.append({'reason':'INTEGRITY_CHECK_FAILED'})
        actual={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        from app.routers.export import EXPORT_WORKFLOW_TABLES,FULL_SYSTEM_TABLES
        for name in EXPORT_WORKFLOW_TABLES+FULL_SYSTEM_TABLES+['questionnaires','feedback','feedback_replies']:
            if name in actual and db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]:
                issues.append({'table':name,'reason':'UNSUPPORTED_CONTINUATION_DATA','action':'新增问答/事实/规则需完整映射，禁止静默丢弃；本导入器仅支持旧版源库'})
        for table in TABLES:
            if table not in actual:
                issues.append({'table':table,'reason':'UNSUPPORTED_MISSING_TABLE'});continue
            rows=[dict(row) for row in db.execute('SELECT * FROM "'+table+'" ORDER BY id')]
            data[table]=rows
            summary[table]={'count':len(rows),'min_id':min((r['id'] for r in rows),default=None),
                'max_id':max((r['id'] for r in rows),default=None)}
        for table,rowid,parent,fkid in db.execute('PRAGMA foreign_key_check'):
            issues.append({'table':table,'id':rowid,'parent_table':parent,'foreign_key':fkid,'reason':'DANGLING_REFERENCE'})
    for table,rows in data.items():
        model=MAPPERS[table]
        for row in rows:
            for column in model.__table__.columns:
                value=row.get(column.name)
                if value is None: continue
                try:
                    if isinstance(column.type,JSON):
                        json.loads(value,parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if isinstance(value,str) else value
                    if isinstance(column.type,Integer) and (type(value) is not int or not -(2**63)<=value<2**63): raise ValueError()
                    if isinstance(column.type,Float) and not math.isfinite(float(value)): raise ValueError()
                    if isinstance(column.type,DateTime): datetime.fromisoformat(value)
                except (ValueError,TypeError):
                    issues.append({'table':table,'id':row['id'],'column':column.name,'reason':'INVALID_TYPE_OR_RANGE'})
                for foreign_key in column.foreign_keys:
                    target=foreign_key.column.table.name
                    found=next((candidate for candidate in data.get(target,[]) if candidate['id']==value),None)
                    if found is None:
                        issues.append({'table':table,'id':row['id'],'column':column.name,'referenced_id':value,'reason':'DANGLING_REFERENCE'})
                    elif row.get('user_id') is not None and found.get('user_id') is not None and row['user_id']!=found['user_id']:
                        issues.append({'table':table,'id':row['id'],'column':column.name,'referenced_id':value,'reason':'CROSS_USER_REFERENCE'})
    semantic_issues, semantic_count = audit(data, MAPPERS)
    issues.extend(semantic_issues)
    return data,{'source_sha256':digest,'tables':summary,'issues':issues,'blocked':bool(issues),
        'non_fk_references':{'checked':semantic_count,'issues':len(semantic_issues)},
        'credentials_policy':'普通设置中的模型密钥不导入；迁入后由本人重新绑定'}


def apply(data, report, url, source_user, username, approved_hash):
    if report['blocked'] or approved_hash!=report['source_sha256']:
        raise ValueError('预检阻断或源哈希未获确认。')
    if not any(row['id']==source_user for row in data['users']): raise ValueError('源账号不存在。')
    engine=create_engine(url,poolclass=NullPool)
    if engine.dialect.name!='postgresql': raise ValueError('正式导入目标必须是 PostgreSQL。')
    mapping={'users':{source_user:None}};deferred=[];written={}
    with Session(engine) as db, db.begin():
        from app.services.transactions import lock_profile
        target=db.query(models.User).filter_by(username=username).one()
        lock_profile(db,target.id)
        mapping['users'][source_user]=target.id
        for name in ('events','ai_judgments','attribute_history','coin_ledger','challenges','goals','redemptions',
                     'achievements','exemptions','daily_reviews','analysis_jobs','llm_credentials','settings','anchor_overrides',
                     'checkin_items','growth_reports','event_derivations','request_receipts'):
            model=MAPPERS[name]
            if db.query(model).filter_by(user_id=target.id).first(): raise ValueError('目标账号已有业务数据，拒绝合并。')
        from app.routers.export import EXPORT_WORKFLOW_TABLES
        for name in EXPORT_WORKFLOW_TABLES:
            model=MAPPERS[name]
            if db.query(model).filter_by(user_id=target.id).first():raise ValueError('目标账号已有续作业务数据，拒绝合并。')
        profile=db.query(models.UserProfile).filter_by(user_id=target.id).one()
        if profile.onboarding_completed or profile.coins: raise ValueError('目标账号已经建档。')
        db.execute(delete(models.Attribute).where(models.Attribute.user_id==target.id))
        db.execute(delete(models.ShopItem).where(models.ShopItem.user_id==target.id))
        for table in Base.metadata.sorted_tables:
            name=table.name
            if name not in TABLES or name=='users': continue
            model=MAPPERS[name];mapping[name]={};written[name]=0
            rows=data[name] if name=='anchors' else [row for row in data[name] if row['user_id']==source_user]
            if name=='attributes': rows=sorted(rows,key=lambda row:(row.get('parent_id') is not None,row['id']))
            for source_row in rows:
                if name=='settings' and source_row['key'].startswith('llm_'): continue
                if name=='anchors':
                    row=db.query(models.Anchor).filter_by(name=source_row['name']).first()
                    if row is None: raise ValueError('存在目标模板不支持的锚点，需另行评审。')
                    mapping[name][source_row['id']]=row.id
                    if source_row.get('calibrated_value') is not None:
                        from app.models.access import AnchorOverride
                        db.add(AnchorOverride(user_id=target.id,anchor_id=row.id,calibrated_value=source_row['calibrated_value']))
                    written[name]+=1
                    continue
                values={}
                for column in table.columns:
                    key=column.name
                    if key=='id' or key not in source_row: continue
                    value=source_row[key]
                    if value is not None:
                        if isinstance(column.type,JSON):
                            value=json.loads(value) if isinstance(value,str) else value
                        elif isinstance(column.type,DateTime):
                            parsed=datetime.fromisoformat(value)
                            if parsed.tzinfo is None:
                                from zoneinfo import ZoneInfo
                                parsed=parsed.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
                            value=parsed
                        elif isinstance(column.type,Boolean): value=bool(value)
                        for fk in column.foreign_keys:
                            value=mapping[fk.column.table.name][value]
                    values[key]=value
                if name=='user_profiles':
                    row=profile
                    for key,value in values.items(): setattr(row,key,value)
                    row.baseline_kind='legacy'
                else:
                    row=model(**values);db.add(row)
                db.flush()
                mapping[name][source_row['id']]=row.id;written[name]+=1
                deferred.append((row,source_row))
        remapped = []
        for row,source_row in deferred:
            def resolve(target, old, path):
                if type(old) is not int or old not in mapping.get(target, {}):
                    raise ValueError(f'未映射引用：{row.__tablename__}#{source_row["id"]}.{path} -> {target}#{old}')
                new = mapping[target][old]
                remapped.append({'table':row.__tablename__,'source_id':source_row['id'],
                    'path':path,'target_table':target,'old_id':old,'new_id':new})
                return new
            for column in row.__table__.columns:
                if isinstance(column.type,JSON):
                    setattr(row,column.name,transform(row.__tablename__,column.name,getattr(row,column.name),resolve))
            if row.__tablename__=='coin_ledger' and row.ref_id is not None:
                row.ref_id=resolve(LEDGER[row.ref_type],source_row['ref_id'],'ref_id')
        db.flush()
        if int(profile.coins)!=int(next(row['coins'] for row in data['user_profiles'] if row['user_id']==source_user)):
            raise ValueError('余额对照失败。')
        # 所有目标 id 均由目标序列分配；无需覆盖或回拨序列。
        result={'written':written,'id_mapping':mapping,'non_fk_mapping':remapped,
            'non_fk_integrity':'PASS','target_user_id':target.id,'source_sha256':report['source_sha256']}
    engine.dispose()
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--report')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--source-user-id',type=int)
    parser.add_argument('--target-username')
    parser.add_argument('--target-dsn-file')
    parser.add_argument('--approve-source-sha256')
    args=parser.parse_args()
    data,report=preflight(args.source)
    if args.apply:
        if hashlib.sha256(Path(args.source).read_bytes()).hexdigest()!=report['source_sha256']:
            raise SystemExit('预检后源文件变化，拒绝导入。')
        if not all([args.source_user_id,args.target_username,args.target_dsn_file,args.approve_source_sha256]):
            parser.error('正式导入要求明确源账号、目标账号、受限 DSN 文件、获准源哈希')
        try:
            report['result']=apply(data,report,Path(args.target_dsn_file).read_text().strip(),args.source_user_id,
                args.target_username,args.approve_source_sha256)
        except Exception as exc:
            report['blocked']=True;report['apply_error']=type(exc).__name__
    output=json.dumps(report,ensure_ascii=False,indent=2)
    if args.report:
        with open(args.report,'x',encoding='utf-8') as target: target.write(output)
    else: print(output)
    return 2 if report['blocked'] else 0


if __name__=='__main__': raise SystemExit(main())
