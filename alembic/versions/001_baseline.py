"""Baseline schema marker — tables created via SQLAlchemy metadata + migrate.py helpers.

Revision ID: 001
Revises:
Create Date: 2026-06-06

Fresh installs use heimdall.db.session.init_db(). Use Alembic for forward-only
schema changes after this baseline.
"""

from typing import Sequence, Union

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
