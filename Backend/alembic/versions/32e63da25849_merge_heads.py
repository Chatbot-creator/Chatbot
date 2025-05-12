"""merge heads

Revision ID: 32e63da25849
Revises: add_property_indexes, f2d24fa550f6
Create Date: 2025-05-12 11:41:01.522538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32e63da25849'
down_revision: Union[str, None] = ('add_property_indexes', 'f2d24fa550f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
