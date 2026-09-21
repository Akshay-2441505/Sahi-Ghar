"""add project_flag table

Revision ID: d4e8a2b6c710
Revises: c3d9f1a7b520
Create Date: 2026-09-21 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4e8a2b6c710'
down_revision: Union[str, Sequence[str], None] = 'c3d9f1a7b520'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('project_flag',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=2), nullable=False),
    sa.Column('rera_reg_no', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('detail', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
    sa.Column('source_document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_document.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('state', 'rera_reg_no', 'kind')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('project_flag')
