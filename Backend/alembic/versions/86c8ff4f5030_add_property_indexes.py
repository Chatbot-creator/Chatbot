"""add_property_indexes

Revision ID: 86c8ff4f5030
Revises: 32e63da25849
Create Date: 2025-05-12 11:41:13.697900

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86c8ff4f5030'
down_revision: Union[str, None] = '32e63da25849'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
