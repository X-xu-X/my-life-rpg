"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b014_rewards_timers'
down_revision = 'b013_care_feedback'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shop_items',sa.Column('reward_kind',sa.String(20),nullable=True))
    op.add_column('shop_items',sa.Column('duration_seconds',sa.Integer(),nullable=True))
    op.add_column('shop_items',sa.Column('base_coin_price',sa.BigInteger(),nullable=True))
    op.add_column('shop_items',sa.Column('repriced_on',sa.String(10),nullable=True))
    op.add_column('redemptions',sa.Column('duration_seconds',sa.Integer(),nullable=True))
    op.create_table('pricing_quotes',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('item_id',sa.Integer(),sa.ForeignKey('shop_items.id'),nullable=True,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('request_key',sa.String(36),nullable=False,primary_key=False),
        sa.Column('fingerprint',sa.String(64),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('context',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('result',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','request_key',name='uq_pricing_request'),
    )
    op.create_table('voucher_allowances',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('redemption_id',sa.Integer(),sa.ForeignKey('redemptions.id'),nullable=False,primary_key=False),
        sa.Column('total_seconds',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('used_seconds',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.UniqueConstraint('redemption_id',name=None),
    )
    op.create_table('time_sessions',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('kind',sa.String(20),nullable=False,primary_key=False),
        sa.Column('source_id',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.Column('last_sync_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.Column('timezone',sa.String(60),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('limit_seconds',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('intervals',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('contract',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('explanation',sa.Text(),nullable=False,primary_key=False),
        sa.Column('analysis',sa.JSON(),nullable=True,primary_key=False),
        sa.Column('preview',sa.JSON(),nullable=True,primary_key=False),
        sa.Column('settlement',sa.JSON(),nullable=True,primary_key=False),
        sa.Column('history',sa.JSON(),nullable=False,primary_key=False),
    )

    op.create_index('uq_active_timer','time_sessions',['user_id'],unique=True,
        postgresql_where=sa.text("state IN ('running','paused','review')"),sqlite_where=sa.text("state IN ('running','paused','review')"))

def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
