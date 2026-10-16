"""Frozen incremental workflow schema; no legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision = 'b008_accounts'
down_revision = 'b007_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users',sa.Column('email',sa.String(254),nullable=True))
    op.add_column('users',sa.Column('email_verified_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('uq_user_email','users',['email'],unique=True)
    op.create_table('site_policies',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
    )
    op.create_table('email_tokens',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=True,primary_key=False),
        sa.Column('email',sa.String(254),nullable=False,primary_key=False),
        sa.Column('purpose',sa.String(20),nullable=False,primary_key=False),
        sa.Column('token_hash',sa.String(64),nullable=False,primary_key=False),
        sa.Column('credentials_version',sa.Integer(),nullable=True,primary_key=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.Column('consumed_at',sa.DateTime(timezone=True),nullable=True,primary_key=False),
        sa.Column('verified',sa.Boolean(),nullable=False,primary_key=False),
        sa.UniqueConstraint('token_hash',name=None),
    )
    op.create_table('announcements',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('title',sa.String(120),nullable=False,primary_key=False),
        sa.Column('content',sa.Text(),nullable=False,primary_key=False),
        sa.Column('published',sa.Boolean(),nullable=False,primary_key=False),
    )
    op.create_table('admin_audits',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('action',sa.String(60),nullable=False,primary_key=False),
        sa.Column('target',sa.String(80),nullable=False,primary_key=False),
        sa.Column('reason',sa.Text(),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )


def downgrade():
    raise RuntimeError('保留事实与历史，使用备份和前向修复回退。')
