"""add project_flag.promoter_ref

Revision ID: e5a1b3c7d902
Revises: d4e8a2b6c710
Create Date: 2026-09-21 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1b3c7d902'
down_revision: Union[str, Sequence[str], None] = 'd4e8a2b6c710'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('project_flag', sa.Column('promoter_ref', sa.String(), nullable=True))
    op.create_index(op.f('ix_project_flag_promoter_ref'), 'project_flag', ['promoter_ref'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_project_flag_promoter_ref'), table_name='project_flag')
    op.drop_column('project_flag', 'promoter_ref')
