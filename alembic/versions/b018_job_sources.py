"""Trace retries and distinguish question-derived sources from explicit answers."""
from alembic import op
import sqlalchemy as sa
revision='b018_job_sources'
down_revision='b017_report_previews'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('review_turns',sa.Column('answer_sources',sa.JSON(),nullable=True))
    op.add_column('analysis_jobs',sa.Column('input_snapshot',sa.JSON(),nullable=True))
def downgrade():
    raise RuntimeError('保留问答授权及任务来源；使用备份回退。')
