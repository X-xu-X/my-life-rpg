"""Optional future constraint proposal; never modifies an active timer contract."""
from alembic import op
import sqlalchemy as sa
revision='b019_phase_suggestions'
down_revision='b018_job_sources'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('personal_phases',sa.Column('pending',sa.JSON(),nullable=True))
def downgrade():
    raise RuntimeError('保留阶段约定建议及审计。')
