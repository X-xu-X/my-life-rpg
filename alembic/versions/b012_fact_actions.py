"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b012_fact_actions'
down_revision = 'b011_record_permissions'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('trial_accounts',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('rule_version',sa.String(30),nullable=False,primary_key=False),
        sa.Column('timezone',sa.String(60),nullable=False,primary_key=False),
        sa.Column('base_minutes',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('region',sa.String(60),nullable=False,primary_key=False),
        sa.Column('contract',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id',name=None),
    )
    op.create_table('daily_entitlements',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('timezone',sa.String(60),nullable=False,primary_key=False),
        sa.Column('first_event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('claimed',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('base_seconds',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('used_seconds',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('rule_version',sa.String(30),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','local_date',name='uq_entitlement_day'),
    )
    op.create_table('fact_fragments',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('event_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('fact_id',sa.Integer(),sa.ForeignKey('fact_identities.id'),nullable=False,primary_key=False),
        sa.Column('fingerprint',sa.String(64),nullable=False,primary_key=False),
        sa.Column('excerpt',sa.Text(),nullable=False,primary_key=False),
        sa.Column('decision',sa.String(20),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','event_id','fingerprint',name='uq_fact_fragment'),
    )
    op.create_table('fact_bundles',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('event_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('permission_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('preview',sa.JSON(),nullable=True,primary_key=False),
        sa.Column('provenance',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('sources',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )
    op.create_table('action_awards',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('fact_id',sa.Integer(),sa.ForeignKey('fact_identities.id'),nullable=False,primary_key=False),
        sa.Column('judgment_id',sa.Integer(),sa.ForeignKey('ai_judgments.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('amount',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('breakdown',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('rule_version',sa.String(30),nullable=False,primary_key=False),
        sa.UniqueConstraint('fact_id',name=None),
        sa.UniqueConstraint('judgment_id',name=None),
    )


def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
