# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""saved jobs have no applied_at

`saved` means "not applied yet", so a saved job with an applied date is a contradiction.
Enforced here as well as in the API.

Revision ID: eb9e45f45dde
Revises: e3521fb119d8
Create Date: 2026-09-25 11:18:24.508370

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eb9e45f45dde"
down_revision: str | Sequence[str] | None = "e3521fb119d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        op.f("ck_jobs_saved_has_no_applied_at"),
        "jobs",
        "status <> 'saved' OR applied_at IS NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_jobs_saved_has_no_applied_at"), "jobs", type_="check")
