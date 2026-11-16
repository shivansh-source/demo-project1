"""baseline

Revision ID: 0001
Revises:
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline revision: establishes the alembic version table.
    # Domain tables arrive in 0002 together with the models.
    pass


def downgrade() -> None:
    pass
