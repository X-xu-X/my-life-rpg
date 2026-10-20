"""Keep related supplements separate from originals and their financial identity."""
from alembic import op
import sqlalchemy as sa
from app.time_types import UTCDateTime
revision='b024_fact_notes'
down_revision='b023_diary_corrections'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('fact_notes',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False),
        sa.Column('event_version',sa.Integer(),nullable=False),
        sa.Column('permission_version',sa.Integer(),nullable=False),
        sa.Column('content',sa.Text(),nullable=False),sa.Column('question_snapshot',sa.JSON(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',UTCDateTime(),nullable=False))

def downgrade():
    raise RuntimeError('保留相关补充及其来源，不自动删除。')
