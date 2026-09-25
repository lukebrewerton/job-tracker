# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""users timezone

Each user's IANA time zone (e.g. Europe/London), for server-side calendar dates: what
"today" is for that user. Validated against zoneinfo by the API; the database only caps
its length.

Revision ID: 676b93a3936b
Revises: eb9e45f45dde
Create Date: 2026-09-25 11:44:02.184529

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "676b93a3936b"
down_revision: str | Sequence[str] | None = "eb9e45f45dde"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("timezone", sa.Text(), server_default="UTC", nullable=False))
    op.create_check_constraint(
        op.f("ck_users_timezone_max_len"), "users", "char_length(timezone) <= 64"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_users_timezone_max_len"), "users", type_="check")
    op.drop_column("users", "timezone")
