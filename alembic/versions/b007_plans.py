"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b007_plans'
down_revision = 'b006_diary'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('plan_schedules',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('name',sa.String(120),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('rule',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )
    op.create_table('plan_occurrences',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('schedule_id',sa.Integer(),sa.ForeignKey('plan_schedules.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('schedule_snapshot',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('outcome',sa.String(20),nullable=False,primary_key=False),
        sa.Column('facts',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=True,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('schedule_id','local_date',name='uq_plan_occurrence'),
    )
    op.create_table('fact_identities',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('identity_key',sa.String(80),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','identity_key',name='uq_fact_identity'),
    )
    op.create_table('event_facts',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('fact_id',sa.Integer(),sa.ForeignKey('fact_identities.id'),nullable=False,primary_key=False),
        sa.UniqueConstraint('event_id',name=None),
    )
    op.create_table('fact_settlements',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('fact_id',sa.Integer(),sa.ForeignKey('fact_identities.id'),nullable=False,primary_key=False),
        sa.Column('judgment_id',sa.Integer(),sa.ForeignKey('ai_judgments.id'),nullable=False,primary_key=False),
        sa.UniqueConstraint('judgment_id',name=None),
        sa.UniqueConstraint('fact_id',name=None),
    )
    op.create_table('fact_relations',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('source_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('target_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('source_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('target_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('reason',sa.Text(),nullable=False,primary_key=False),
    )


def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
