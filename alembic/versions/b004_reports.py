"""保留报告及来源版本，不写事实或经济账。"""
from alembic import op
import sqlalchemy as sa
revision = 'b004_reports'
down_revision = 'b003_analysis'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('growth_reports', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('period', sa.String(20), nullable=False),
        sa.Column('timezone', sa.String(60), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('provenance', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError('禁止自动删除历史报告，请按恢复手册回退。')
