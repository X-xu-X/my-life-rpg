"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b013_care_feedback'
down_revision = 'b012_fact_actions'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('care_configs',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('initialized',sa.Boolean(),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id',name=None),
    )
    op.create_table('care_items',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('name',sa.String(80),nullable=False,primary_key=False),
        sa.Column('position',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('removed',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('rule',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
    )
    op.create_table('care_entries',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('item_id',sa.Integer(),sa.ForeignKey('care_items.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=True,primary_key=False),
        sa.Column('snapshot',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('item_id','local_date',name='uq_care_occurrence'),
    )
    op.create_table('feedback',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('kind',sa.String(20),nullable=False,primary_key=False),
        sa.Column('title',sa.String(120),nullable=False,primary_key=False),
        sa.Column('content',sa.Text(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )
    op.create_table('feedback_replies',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('feedback_id',sa.Integer(),sa.ForeignKey('feedback.id'),nullable=False,primary_key=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('content',sa.Text(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )


def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
