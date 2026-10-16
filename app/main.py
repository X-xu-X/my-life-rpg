"""游戏人生（Game of Life）FastAPI 应用入口。

本地运行：uvicorn app.main:app --reload
首次启动会自动创建 SQLite 表（等价于执行 sql/schema.sql）。
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine, migrate_schema
from app.config import settings
from app.services.auth_service import current_user
from app.services import owned_repository
from app.routers import auth, baseline, analysis, review, diary, plans, admin, account_security
from app import models  # noqa: F401  导入以注册所有 ORM 模型到 Base.metadata
from app.routers import (
    achievements,
    onboarding,
    events,
    judgments,
    attributes,
    goals,
    items,
    coins,
    challenges,
    shop,
    exemptions,
    subdimensions,
    stagnation,
    anchors,
    export,
    report,
    settings as settings_router,
)

app = FastAPI(
    title="游戏人生（Game of Life）",
    description="AI 驱动的个人成长游戏化系统 —— 记录生活事件，AI 依据科学标准判定属性点增减。",
    version="0.1.0",
)

# 允许前端 Vite 开发服务器跨域访问（本地开发）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_origin] if settings.cloud else ["http://localhost:5173", "http://127.0.0.1:5173"],  # V1 本地自用放宽；上云后应收紧为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(onboarding.router, prefix="/api", tags=["onboarding"], dependencies=[Depends(current_user)])
app.include_router(events.router, prefix="/api", tags=["events"], dependencies=[Depends(current_user)])
app.include_router(judgments.router, prefix="/api", tags=["judgments"], dependencies=[Depends(current_user)])
app.include_router(attributes.router, prefix="/api", tags=["attributes"], dependencies=[Depends(current_user)])
app.include_router(goals.router, prefix="/api", tags=["goals"], dependencies=[Depends(current_user)])
app.include_router(items.router, prefix="/api", tags=["items"], dependencies=[Depends(current_user)])
app.include_router(coins.router, prefix="/api", tags=["coins"], dependencies=[Depends(current_user)])
app.include_router(achievements.router, prefix="/api", tags=["achievements"], dependencies=[Depends(current_user)])
app.include_router(challenges.router, prefix="/api", tags=["challenges"], dependencies=[Depends(current_user)])
app.include_router(shop.router, prefix="/api", tags=["shop"], dependencies=[Depends(current_user)])
app.include_router(exemptions.router, prefix="/api", tags=["exemptions"], dependencies=[Depends(current_user)])
app.include_router(subdimensions.router, prefix="/api", tags=["subdimensions"], dependencies=[Depends(current_user)])
app.include_router(stagnation.router, prefix="/api", tags=["stagnation"], dependencies=[Depends(current_user)])
app.include_router(anchors.router, prefix="/api", tags=["anchors"], dependencies=[Depends(current_user)])
app.include_router(settings_router.router, prefix="/api", tags=["settings"], dependencies=[Depends(current_user)])
app.include_router(export.router, prefix="/api", tags=["export"], dependencies=[Depends(current_user)])
app.include_router(report.router, prefix="/api", tags=["report"], dependencies=[Depends(current_user)])


app.include_router(analysis.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(review.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(baseline.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(plans.router, prefix='/api', dependencies=[Depends(current_user)])
app.include_router(diary.router, prefix='/api', dependencies=[Depends(current_user)])
app.include_router(admin.router,prefix='/api')
app.include_router(admin.public,prefix='/api',dependencies=[Depends(current_user)])
app.include_router(account_security.router,prefix='/api')
app.include_router(auth.router, prefix="/api", tags=["auth"])


@app.on_event("startup")
def init_db():
    """启动时初始化：建表 + 轻量迁移 + 写入内置锚点 + 创建默认用户（均幂等）。"""
    if settings.cloud:
        from sqlalchemy import text
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from pathlib import Path
        if not settings.db_url or not settings.public_origin.startswith("https://") or not settings.credential_key_file:
            raise RuntimeError("云模式要求显式 DB_URL、HTTPS PUBLIC_ORIGIN 和 CREDENTIAL_KEY_FILE。")
        if engine.dialect.name == "sqlite" and not settings.allow_cloud_sqlite:
            raise RuntimeError("SQLite 云模式仅限显式允许的单实例试验。")
        with engine.connect() as connection:
            actual = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        expected = set(ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))).get_heads())
        if actual != expected:
            raise RuntimeError("数据库版本未就绪，请先单独执行迁移。")
        from app.services.credentials import keyring
        keyring()
        return
    from app.services.backup_service import backup_now
    backup_now()  # 已有数据库必须在迁移之前留原始副本
    Base.metadata.create_all(bind=engine)
    migrate_schema(engine)  # 为已有表补充模型新增的缺失列（如 ai_judgments.analysis）
    from app.database import SessionLocal
    from app.services.anchor_service import seed_anchors
    from app.services.user_service import ensure_dimensions, get_or_create_default_user

    db = SessionLocal()
    try:
        seed_anchors(db)  # 内置锚点幂等写入
        user = get_or_create_default_user(db)  # V1 单用户
        ensure_dimensions(db, user)  # 补全全部标准维度（维度扩展后给老用户补新维度）
    finally:
        db.close()



@app.get("/api/health")
def health():
    """健康检查。"""
    return {"status": "ok", "app": "game-of-life"}


@app.get('/api/ready')
def ready():
    from sqlalchemy import text
    from fastapi import HTTPException
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status':'ready'}
    except Exception:
        raise HTTPException(503, '数据库未就绪。') from None
