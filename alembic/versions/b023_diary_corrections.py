"""Explicit source corrections retain all bookings and original versions."""
from alembic import op
import sqlalchemy as sa
revision='b023_diary_corrections'
down_revision='b022_focus_sources'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('diary_revisions',sa.Column('correction_reason',sa.Text(),nullable=True))
def downgrade():
    raise RuntimeError('保留原文更正说明及历史。')
