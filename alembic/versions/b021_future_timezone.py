"""Rule timezone changes start next old-zone day; existing entitlements stay fixed."""
from alembic import op
import sqlalchemy as sa
revision='b021_future_timezone'
down_revision='b020_derived_sources'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('trial_accounts',sa.Column('pending_timezone',sa.String(60),nullable=True))
    op.add_column('trial_accounts',sa.Column('timezone_effective_at',sa.DateTime(timezone=True),nullable=True))
def downgrade():
    raise RuntimeError('保留日规则时区合同，不允许丢失权益身份。')
