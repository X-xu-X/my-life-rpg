"""Durable recovery queue and safe account/plan metadata; no historical rewrite."""
from alembic import op
import sqlalchemy as sa
revision='b010_review_repairs'
down_revision='b009_policies'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('users',sa.Column('last_login_at',sa.DateTime(timezone=True),nullable=True))
    if op.get_bind().dialect.name=='sqlite':op.execute('ALTER TABLE plan_schedules ADD COLUMN goal_id INTEGER REFERENCES goals(id)')
    else:op.add_column('plan_schedules',sa.Column('goal_id',sa.Integer(),sa.ForeignKey('goals.id'),nullable=True))
    op.create_table('mail_deliveries',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('email',sa.String(254),nullable=False),sa.Column('purpose',sa.String(20),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('lease_token',sa.String(64),nullable=True),sa.Column('next_attempt',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('encrypted_key',sa.Text(),nullable=True),
        sa.Column('key_id',sa.String(30),nullable=True),sa.Column('token_id',sa.Integer(),sa.ForeignKey('email_tokens.id'),nullable=True),
        sa.Column('error_code',sa.String(40),nullable=True))


def downgrade():
    raise RuntimeError('保留投递任务及历史元数据；请用备份回退，禁止破坏性降级。')
