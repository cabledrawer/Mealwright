"""add single sign-on

Revision ID: c1d5e9a3f702
Revises: c7a1e5d3f802
Create Date: 2026-11-14 09:00:00

Single sign-on (0.9, PR O1), its one database change.

- `sso_settings`: the household's single sign-on setup, one row when it is set up. The client
  secret is kept sealed (encrypted with the key file in the data folder), never as typed.
- `login.sso_issuer` and `login.sso_subject`: who a login is at the sign-in server. A login is
  found only by both together (unique), never by a name or email address.
- `session.sso`, `session.sso_refresh_sealed` and `session.sso_check_at`: a sign-in made with
  single sign-on, its sealed refresh token, and when it is next checked.

Everything new starts empty, and password sign-in stays on, so nothing changes until an admin
sets single sign-on up. Going back drops the table and the columns: single sign-on's setup, the
links between logins and the sign-in server, and the refresh tokens are lost; every login and
session stays (a login made by single sign-on stays, with no password).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d5e9a3f702"
down_revision: str | Sequence[str] | None = "c7a1e5d3f802"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sso_settings",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_sealed", sa.Text(), nullable=True),
        sa.Column("button_name", sa.String(length=60), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("group_claim", sa.String(length=100), nullable=False),
        sa.Column("group_roles", sa.JSON(), nullable=False),
        sa.Column("anyone_else", sa.String(length=10), nullable=False),
        sa.Column("make_accounts", sa.Boolean(), nullable=False),
        sa.Column("password_sign_in", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "anyone_else IN ('none', 'member')", name=op.f("ck_sso_settings_anyone_else_known")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_sso_settings_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("household_id", name=op.f("pk_sso_settings")),
    )
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sso_issuer", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("sso_subject", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_login_sso", ["sso_issuer", "sso_subject"])
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("sso", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.add_column(sa.Column("sso_refresh_sealed", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("sso_check_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_column("sso_check_at")
        batch_op.drop_column("sso_refresh_sealed")
        batch_op.drop_column("sso")
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.drop_constraint("uq_login_sso", type_="unique")
        batch_op.drop_column("sso_subject")
        batch_op.drop_column("sso_issuer")
    op.drop_table("sso_settings")
