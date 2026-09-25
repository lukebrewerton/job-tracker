# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""interview mode optional

An interview is often recorded as soon as it's offered, before the mode (remote, in
person, phone) is known. Like scheduled_at, it stays empty until known rather than
being forced to a made-up value.

Revision ID: eee6f4152385
Revises: 676b93a3936b
Create Date: 2026-09-25 12:37:50

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eee6f4152385"
down_revision: str | Sequence[str] | None = "676b93a3936b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("interviews", "mode", existing_type=sa.String(length=32), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Interviews recorded without a mode would block the downgrade; give them one.
    op.execute("UPDATE interviews SET mode = 'remote' WHERE mode IS NULL")
    op.alter_column("interviews", "mode", existing_type=sa.String(length=32), nullable=False)
