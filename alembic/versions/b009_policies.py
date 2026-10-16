"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b009_policies'
down_revision = 'b008_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events',sa.Column('saved_on',sa.String(10),nullable=True))
    op.add_column('events',sa.Column('saved_timezone',sa.String(60),nullable=True))
    op.create_table('economic_rules',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('kind',sa.String(20),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('kind','version',name='uq_economic_rule_version'),
    )
    op.create_table('mainlines',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('goal_id',sa.Integer(),sa.ForeignKey('goals.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('active',sa.Boolean(),nullable=False,primary_key=False),
    )
    op.create_table('reward_previews',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('mainline_id',sa.Integer(),sa.ForeignKey('mainlines.id'),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('judgment_id',sa.Integer(),sa.ForeignKey('ai_judgments.id'),nullable=False,primary_key=False),
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('economic_rules.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('snapshot',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('amount',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )
    op.create_table('mainline_awards',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('fact_id',sa.Integer(),sa.ForeignKey('fact_identities.id'),nullable=False,primary_key=False),
        sa.Column('preview_id',sa.Integer(),sa.ForeignKey('reward_previews.id'),nullable=False,primary_key=False),
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('economic_rules.id'),nullable=False,primary_key=False),
        sa.Column('cap_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('amount',sa.BigInteger(),nullable=False,primary_key=False),
        sa.UniqueConstraint('fact_id',name=None),
        sa.UniqueConstraint('preview_id',name=None),
    )
    op.create_table('dynamic_candidates',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('semantic_key',sa.String(64),nullable=False,primary_key=False),
        sa.Column('name',sa.String(100),nullable=False,primary_key=False),
        sa.Column('criteria',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('evidence',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','semantic_key',name='uq_dynamic_semantics'),
    )
    op.create_table('dynamic_awards',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('equivalence_key',sa.String(80),nullable=True,primary_key=False),
        sa.Column('candidate_id',sa.Integer(),sa.ForeignKey('dynamic_candidates.id'),nullable=False,primary_key=False),
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('economic_rules.id'),nullable=False,primary_key=False),
        sa.Column('achievement_id',sa.Integer(),sa.ForeignKey('achievements.id'),nullable=False,primary_key=False),
        sa.Column('amount',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('evidence',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('candidate_id',name=None),
        sa.UniqueConstraint('achievement_id',name=None),
        sa.UniqueConstraint('user_id','equivalence_key',name='uq_dynamic_fixed_equivalence'),
    )
    op.create_table('hosted_ai',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('enabled',sa.Boolean(),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
    )
    op.create_table('ai_preferences',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('mode',sa.String(20),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id',name=None),
    )
    op.create_table('hosted_usage',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('hosted_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('pricing_snapshot',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('reserved_tokens',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('charged_tokens',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('reserved_cost',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('charged_cost',sa.BigInteger(),nullable=False,primary_key=False),
        sa.Column('safe_error_code',sa.String(50),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )


def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
