"""Daily experience archives, preferences, calendar and bounded price jobs."""
from alembic import op
import sqlalchemy as sa
from app.time_types import UTCDateTime
revision='b025_daily_use'
down_revision='b024_fact_notes'
branch_labels=None
depends_on=None


def owner_columns():
    return [sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('version',sa.Integer(),nullable=False)]


def upgrade():
    op.add_column('shop_items',sa.Column('auto_pricing',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('shop_items',sa.Column('description',sa.Text(),nullable=False,server_default=''))
    op.add_column('shop_items',sa.Column('priced_at',UTCDateTime(),nullable=True))
    for name in ('question_snapshot','followups','history'):
        op.add_column('questionnaires',sa.Column(name,sa.JSON(),nullable=False,server_default=sa.text("'[]'")))
    op.add_column('questionnaires',sa.Column('uses',sa.JSON(),nullable=False,server_default=sa.text("'[\"judge\",\"review\",\"report\",\"pricing\"]'")))
    op.add_column('questionnaires',sa.Column('stage',sa.String(20),nullable=False,server_default='basics'))
    op.create_table('personal_information',*owner_columns(),sa.Column('entries',sa.JSON(),nullable=False),sa.Column('updated_at',UTCDateTime(),nullable=False),sa.UniqueConstraint('user_id'))
    op.create_table('experience_preferences',*owner_columns(),sa.Column('suppressed',sa.JSON(),nullable=False),sa.Column('return_disabled',sa.Boolean(),nullable=False),sa.Column('review_snoozed_until',UTCDateTime(),nullable=True),sa.UniqueConstraint('user_id'))
    op.create_table('return_checkins',*owner_columns(),sa.Column('answers',sa.JSON(),nullable=False),sa.Column('uses',sa.JSON(),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('history',sa.JSON(),nullable=False),sa.Column('updated_at',UTCDateTime(),nullable=False),sa.UniqueConstraint('user_id'))
    op.create_table('important_days',*owner_columns(),sa.Column('name',sa.String(120),nullable=False),sa.Column('month',sa.Integer(),nullable=False),sa.Column('day',sa.Integer(),nullable=False),sa.Column('year',sa.Integer(),nullable=True),sa.Column('annual',sa.Boolean(),nullable=False),sa.Column('remind_days',sa.Integer(),nullable=False),sa.Column('enabled',sa.Boolean(),nullable=False))
    op.create_table('official_calendars',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('year',sa.Integer(),nullable=False,unique=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('source_url',sa.Text(),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('data',sa.JSON(),nullable=False))
    op.create_table('model_dispatches',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('operation',sa.String(100),nullable=False),sa.Column('request_key',sa.String(36),nullable=False),sa.Column('payload_hash',sa.String(64),nullable=False),sa.Column('created_at',UTCDateTime(),nullable=False),sa.UniqueConstraint('user_id','operation','request_key',name='uq_model_dispatch_key'))
    op.create_table('pricing_checks',*owner_columns(),sa.Column('item_id',sa.Integer(),sa.ForeignKey('shop_items.id'),nullable=False),sa.Column('local_date',sa.String(10),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('request_key',sa.String(36),nullable=False),sa.Column('lease_token',sa.String(36),nullable=True),sa.Column('started_at',UTCDateTime(),nullable=True),sa.Column('completed_at',UTCDateTime(),nullable=True),sa.Column('error_code',sa.String(50),nullable=True),sa.Column('quote_id',sa.Integer(),sa.ForeignKey('pricing_quotes.id'),nullable=True),sa.UniqueConstraint('user_id','item_id','local_date',name='uq_pricing_check_day'))


def downgrade():
    raise RuntimeError('保留问卷/近况和价格历史，请从升级前一致备份隔离恢复，不自动删档。')
