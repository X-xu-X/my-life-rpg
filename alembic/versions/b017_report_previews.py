"""New reports need explicit save; existing saved reports retain their identity."""
from alembic import op
import sqlalchemy as sa
revision='b017_report_previews'
down_revision='b016_custom_endpoints'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('growth_reports',sa.Column('state',sa.String(20),nullable=False,server_default='legacy_saved'))
    op.add_column('growth_reports',sa.Column('version',sa.Integer(),nullable=False,server_default='1'))
def downgrade():
    raise RuntimeError('保留报告预览与已保存身份；使用备份回退。')
