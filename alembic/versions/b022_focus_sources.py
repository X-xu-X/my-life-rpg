"""Explicit focus-name scope and per-question configuration provenance."""
from alembic import op
import sqlalchemy as sa
revision='b022_focus_sources'
down_revision='b021_future_timezone'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('care_configs',sa.Column('ai_allowed',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('care_configs',sa.Column('suggestions',sa.JSON(),nullable=True))
    op.add_column('review_turns',sa.Column('background',sa.String(64),nullable=True))
def downgrade():
    raise RuntimeError('保留关注项目许可与历史问答来源。')
