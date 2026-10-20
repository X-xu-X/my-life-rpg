"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b015_profiles_calendar'
down_revision = 'b014_rewards_timers'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('questionnaires',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('answers',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('send_groups',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('preview',sa.JSON(),nullable=True,primary_key=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id',name=None),
    )
    op.create_table('personal_phases',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('return_cooldown_until',sa.DateTime(timezone=True),nullable=True,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id',name=None),
    )
    op.create_table('holidays',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('region',sa.String(60),nullable=False,primary_key=False),
        sa.Column('name',sa.String(120),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
    )
    op.create_table('holiday_claims',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('amount',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('snapshot',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','local_date',name='uq_holiday_claim_day'),
    )


def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
