"""add project.extension_history

Revision ID: c3d9f1a7b520
Revises: b7c1e2f4a9d3
Create Date: 2026-09-21 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3d9f1a7b520'
down_revision: Union[str, Sequence[str], None] = 'b7c1e2f4a9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('project', sa.Column('extension_history', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('project', 'extension_history')
