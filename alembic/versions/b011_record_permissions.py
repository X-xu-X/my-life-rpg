"""Private-by-default permission; unknown legacy summaries remain quarantined."""
from alembic import op
import sqlalchemy as sa
revision='b011_record_permissions'
down_revision='b010_review_repairs'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('events',sa.Column('ai_permission',sa.String(12),server_default='private',nullable=False))
    op.add_column('events',sa.Column('ai_permission_version',sa.Integer(),server_default='1',nullable=False))
    op.add_column('events',sa.Column('ai_permission_changed_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('analysis_jobs',sa.Column('permission_version',sa.Integer(),nullable=True))
    op.add_column('ai_judgments',sa.Column('source_snapshot',sa.JSON(),nullable=True))
    op.add_column('user_profiles',sa.Column('memory_sources',sa.JSON(),nullable=True))
    op.add_column('review_turns',sa.Column('ai_sources',sa.JSON(),nullable=True))

def downgrade():
    raise RuntimeError('禁止丢弃逐篇许可和来源；需要维护窗口恢复备份。')
