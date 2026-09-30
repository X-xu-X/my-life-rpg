"""游戏人生（Game of Life）FastAPI 应用入口。

本地运行：uvicorn app.main:app --reload
首次启动会自动创建 SQLite 表（等价于执行 sql/schema.sql）。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine, migrate_schema
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
    allow_origins=["*"],  # V1 本地自用放宽；上云后应收紧为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(onboarding.router, prefix="/api", tags=["onboarding"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(judgments.router, prefix="/api", tags=["judgments"])
app.include_router(attributes.router, prefix="/api", tags=["attributes"])
app.include_router(goals.router, prefix="/api", tags=["goals"])
app.include_router(items.router, prefix="/api", tags=["items"])
app.include_router(coins.router, prefix="/api", tags=["coins"])
app.include_router(achievements.router, prefix="/api", tags=["achievements"])
app.include_router(challenges.router, prefix="/api", tags=["challenges"])
app.include_router(shop.router, prefix="/api", tags=["shop"])
app.include_router(exemptions.router, prefix="/api", tags=["exemptions"])
app.include_router(stagnation.router, prefix="/api", tags=["stagnation"])
app.include_router(anchors.router, prefix="/api", tags=["anchors"])
app.include_router(settings_router.router, prefix="/api", tags=["settings"])
app.include_router(export.router, prefix="/api", tags=["export"])
app.include_router(report.router, prefix="/api", tags=["report"])


@app.on_event("startup")
def init_db():
    """启动时初始化：建表 + 轻量迁移 + 写入内置锚点 + 创建默认用户（均幂等）。"""
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

    # 启动时自动备份数据库（SQLite backup API，失败不影响启动）
    from app.services.backup_service import backup_now

    backup_now()


@app.get("/api/health")
def health():
    """健康检查。"""
    return {"status": "ok", "app": "game-of-life"}
