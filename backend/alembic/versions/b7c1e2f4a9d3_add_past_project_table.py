"""add past_project table

Revision ID: b7c1e2f4a9d3
Revises: a55d84882074
Create Date: 2026-09-21 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1e2f4a9d3'
down_revision: Union[str, Sequence[str], None] = 'a55d84882074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('past_project',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('promoter_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('project_type', sa.String(), nullable=True),
    sa.Column('original_proposed_date', sa.Date(), nullable=False),
    sa.Column('actual_completion_date', sa.Date(), nullable=False),
    sa.Column('source_document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['promoter_id'], ['promoter.id'], ),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_document.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('promoter_id', 'name', 'original_proposed_date')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('past_project')
