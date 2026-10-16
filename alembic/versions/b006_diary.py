"""Explicit diary originals and recoverable review sessions; no legacy backfill."""
from alembic import op
import sqlalchemy as sa
revision = 'b006_diary'
down_revision = 'b005_trial_p1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events',sa.Column('record_kind',sa.String(20),nullable=True))
    op.add_column('events',sa.Column('diary_key',sa.String(80),nullable=True))
    op.create_index('uq_event_diary_key','events',['diary_key'],unique=True)

    op.create_table('diary_revisions',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('content',sa.Text(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('event_id','version',name='uq_diary_revision'),
    )
    op.create_table('review_sessions',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('diary_id',sa.Integer(),sa.ForeignKey('events.id'),nullable=False,primary_key=False),
        sa.Column('source_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('sources',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','diary_id','source_version',name='uq_diary_session'),
    )
    op.create_table('review_turns',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('session_id',sa.Integer(),sa.ForeignKey('review_sessions.id'),nullable=False,primary_key=False),
        sa.Column('ordinal',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('question',sa.Text(),nullable=False,primary_key=False),
        sa.Column('answer',sa.Text(),nullable=False,primary_key=False),
        sa.Column('state',sa.String(20),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
        sa.UniqueConstraint('session_id','ordinal',name='uq_review_turn'),
    )
    op.create_table('review_analyses',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('session_id',sa.Integer(),sa.ForeignKey('review_sessions.id'),nullable=False,primary_key=False),
        sa.Column('session_version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('provenance',sa.JSON(),nullable=False,primary_key=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,primary_key=False),
    )
    op.create_table('life_checklists',
        sa.Column('id',sa.Integer(),nullable=False,primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,primary_key=False),
        sa.Column('local_date',sa.String(10),nullable=False,primary_key=False),
        sa.Column('version',sa.Integer(),nullable=False,primary_key=False),
        sa.Column('payload',sa.JSON(),nullable=False,primary_key=False),
        sa.UniqueConstraint('user_id','local_date',name='uq_checklist_day'),
    )
    op.add_column('analysis_jobs',sa.Column('review_session_id',sa.Integer(),nullable=True))
    op.add_column('analysis_jobs',sa.Column('session_version',sa.Integer(),nullable=True))
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key('fk_job_review_session','analysis_jobs','review_sessions',['review_session_id'],['id'])


def downgrade():
    raise RuntimeError('保留日记和完整问答，请按备份与前向修复流程回退。')
