"""Experience preference: suppressed tip lines."""
from alembic import op
import sqlalchemy as sa
revision='b027_suppressed_lines'
down_revision='b026_pricing_mode'
branch_labels=None
depends_on=None


def upgrade():
    # b025 建表时漏了这一列（本地 SQLite 靠 migrate_schema 补上，云端一直没有）。
    # 模型是 nullable=True：老行留 NULL，读取处一律 `or []`。
    op.add_column('experience_preferences',sa.Column('suppressed_lines',sa.JSON(),nullable=True))


def downgrade():
    raise RuntimeError('用户已关闭的提示行不自动回退，请从升级前备份隔离恢复。')
