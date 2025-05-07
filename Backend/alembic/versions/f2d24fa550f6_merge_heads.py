"""Merge heads

Revision ID: f2d24fa550f6
Revises: 53d7f52fb8c1, a2e4d7c83f4a
Create Date: 2025-05-05 15:06:40.887365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2d24fa550f6'
down_revision: Union[str, None] = ('53d7f52fb8c1', 'a2e4d7c83f4a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
