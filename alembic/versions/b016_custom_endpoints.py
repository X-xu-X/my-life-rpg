"""Custom endpoints use pinned public HTTPS transport, never plain HTTP."""
from alembic import op
import sqlalchemy as sa
revision='b016_custom_endpoints'
down_revision='b015_profiles_calendar'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('llm_credentials',sa.Column('base_url',sa.String(300),nullable=True))
    op.add_column('events',sa.Column('economy_version',sa.String(30),nullable=True))
def downgrade():
    raise RuntimeError('保留凭据绑定边界；用备份或前向修复回退。')
