"""Add voice messages table

Revision ID: add_voice_messages
Create Date: 2025-05-15 12:48:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'add_voice_messages'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
from alembic import op
import sqlalchemy as sa

def upgrade():
    # create voice_messages table
    op.create_table(
        'voice_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('file_data', sa.LargeBinary(), nullable=True),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('transcribed_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_messages_id'), 'voice_messages', ['id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_voice_messages_id'), table_name='voice_messages')
    op.drop_table('voice_messages')
