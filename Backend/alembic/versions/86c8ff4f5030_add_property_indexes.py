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
    """Add indexes for better query performance."""
    # Create indexes for commonly queried fields
    op.create_index('idx_property_created_at', 'properties', ['created_at'])
    op.create_index('idx_property_updated_at', 'properties', ['updated_at'])
    op.create_index('idx_property_type', 'properties', ['property_type_id'])
    op.create_index('idx_property_district', 'properties', ['district_id'])
    op.create_index('idx_property_price', 'properties', ['price'])


def downgrade() -> None:
    """Remove the indexes."""
    # Remove the indexes
    op.drop_index('idx_property_created_at')
    op.drop_index('idx_property_updated_at')
    op.drop_index('idx_property_type')
    op.drop_index('idx_property_district')
    op.drop_index('idx_property_price')
