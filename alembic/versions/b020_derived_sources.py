"""Quarantine untraceable derived names from subsequent model context."""
from alembic import op
import sqlalchemy as sa
revision='b020_derived_sources'
down_revision='b019_phase_suggestions'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('attributes',sa.Column('ai_sources',sa.JSON(),nullable=True))
    op.add_column('challenges',sa.Column('ai_sources',sa.JSON(),nullable=True))
def downgrade():
    raise RuntimeError('保留派生建议的来源，不允许无来源回退。')
