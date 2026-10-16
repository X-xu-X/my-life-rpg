"""Optional event date precision; historical timestamps remain untouched."""
from alembic import op
import sqlalchemy as sa
revision = 'b005_trial_p1'
down_revision = 'b004_reports'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('occurred_on', sa.String(10), nullable=True))
    op.add_column('events', sa.Column('time_precision', sa.String(10), nullable=True))
    op.add_column('ai_judgments', sa.Column('model_provenance', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('ai_judgments', 'model_provenance')
    op.drop_column('events', 'time_precision')
    op.drop_column('events', 'occurred_on')
