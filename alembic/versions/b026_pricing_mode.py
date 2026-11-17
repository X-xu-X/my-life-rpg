"""Shop item pricing mode (once / recurring)."""
from alembic import op
import sqlalchemy as sa
revision='b026_pricing_mode'
down_revision='b025_daily_use'
branch_labels=None
depends_on=None


def upgrade():
    # server_default 让既有行在加列瞬间就满足 NOT NULL；随后同一次 upgrade 里回填。
    op.add_column('shop_items',sa.Column('pricing_mode',sa.String(10),nullable=False,server_default='once'))
    # 旧开关 auto_pricing 为真的商品继续按「常用兑换券」重估，其余落 once。
    # `IS TRUE` 而不是 `= 1`：PostgreSQL 不允许 boolean 与 integer 比较（SQLite 宽容）。
    op.execute("UPDATE shop_items SET pricing_mode='recurring' WHERE auto_pricing IS TRUE")


def downgrade():
    raise RuntimeError('价格历史与既定定价方式不自动回退，请从升级前备份隔离恢复。')
