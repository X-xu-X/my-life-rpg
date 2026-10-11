"""受限终端管理；口令交互输入，秘密只在初始化时显示一次。"""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['generate-key','init-owner','invite','rotate-credentials'])
    parser.add_argument('--username')
    parser.add_argument('--output')
    args=parser.parse_args()
    if args.operation=='generate-key':
        from cryptography.fernet import Fernet
        if not args.output: parser.error('--output 必填；已有文件不会覆盖')
        with open(args.output,'x',encoding='utf-8') as target:
            os.chmod(args.output,0o600)
            json.dump({'active':'v1','keys':{'v1':Fernet.generate_key().decode()}},target)
        print('主密钥文件已生成，请另存离线副本。')
        return
    if not os.environ.get('DB_URL'): parser.error('必须显式提供 DB_URL')
    from app.database import SessionLocal
    from app.models import User
    import app.models.access, app.models.analysis
    from app.services import auth_service, anchor_service, credentials
    with SessionLocal() as db:
        if args.operation=='rotate-credentials':
            from app.models.access import LLMCredential
            from app.services.transactions import lock_profile
            active, keys=credentials.keyring()
            user_ids=[value for value, in db.query(LLMCredential.user_id).distinct().order_by(LLMCredential.user_id)]
            for user_id in user_ids: lock_profile(db,user_id)
            rows=db.query(LLMCredential).order_by(LLMCredential.user_id,LLMCredential.id).with_for_update().all()
            for row in rows:
                if row.encrypted_key:
                    row.encrypted_key=keys[active].encrypt(credentials.decrypt(row).encode()).decode()
                    row.key_id=active
                    row.config_version+=1
            db.commit()
            print(f'已轮换 {len(rows)} 组配置；保留旧 key_id，直到旧备份过期。')
            return
        if not args.username: parser.error('--username 必填')
        user=db.query(User).filter_by(username=args.username).first()
        if args.operation=='init-owner':
            if user or db.query(User).filter_by(role='owner').first():
                parser.error('已有所有者或同名账号，拒绝覆盖')
            password=getpass.getpass('所有者密码（至少 12 字符）：')
            if not 12<=len(password)<=256 or password!=getpass.getpass('再输入一次：'): parser.error('密码不符合要求或两次不一致')
            user=auth_service.initialize_account(db,args.username,password,role='owner')
            anchor_service.seed_anchors(db, commit=False)
            recovery=auth_service.new_recovery(db,user)
            db.commit()
            print('所有者已创建；恢复码只显示本次：'+recovery)
        else:
            if not user or user.role!='owner' or user.status!='active': parser.error('有效所有者不存在')
            token=auth_service.issue_invitation(db,user)
            db.commit()
            print('72 小时内一次性邀请令牌：'+token)


if __name__=='__main__': main()
