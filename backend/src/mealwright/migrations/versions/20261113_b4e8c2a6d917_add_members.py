"""add people (members), shared logins, "Who's this?" and one-time sign-in links

Revision ID: b4e8c2a6d917
Revises: a9d3f6b2c481
Create Date: 2026-11-13 09:00:00

People and roles (0.9 A1; spec section 3, "Users and households", cabledrawer 17 Oct; "Members later
getting a login: yes, Admin only, from Settings → Household; portions and history stay with
them", cabledrawer 11 Nov).

- New table `member`: a person of the household (name, colour, portion in quarters, removed).
  Each login there now gets its own person with the same name and one portion, numbered the same
  as the login, so every link that named a login still names the same person.
- `login.member_id` (that person) and `login.shared` (no: no login is shared yet).
- `session.member_id`: who picked themselves in "Who's this?" on a shared login (empty).
- `change.member_id`: who did it. Filled in for every change a login made, with its person.
- `tub.member_login_id` becomes `tub.member_id`, and `meal_eater.login_id` becomes
  `meal_eater.member_id`, pointing at the same people. Recent changes' Undo records that name
  them use the new names too.
- New table `join_link` (empty): the one-time sign-in links an admin makes.
- `household.ask_whos_this` (off).

Going back puts the tubs and who's eating back on the logins (a person without a login is
dropped from them), drops the new tables and columns, and puts the Undo records' names back.
What is lost: people without a login, colours and portions, shared-login marks, unused sign-in
links, and who picked themselves in "Who's this?".
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8c2a6d917"
down_revision: str | Sequence[str] | None = "a9d3f6b2c481"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}

# Undo-record keys that name people: (old, new). A list of eaters is "login_ids" only inside an
# {"op": "eaters"} step; tubs carry "member_login_id" anywhere.
_TUB_KEYS = (("member_login_id", "member_id"), ("member_login_ids", "member_ids"))


def _rename(value: Any, forward: bool) -> Any:
    if isinstance(value, list):
        return [_rename(v, forward) for v in value]
    if not isinstance(value, dict):
        return value
    pairs = [(old, new) if forward else (new, old) for old, new in _TUB_KEYS]
    if value.get("op") == "eaters":
        pairs.append(("login_ids", "member_ids") if forward else ("member_ids", "login_ids"))
    names = dict(pairs)
    return {names.get(k, k): _rename(v, forward) for k, v in value.items()}


def _rewrite_undo_records(forward: bool) -> None:
    bind = op.get_bind()
    words = ("member_login_id", '%"eaters"%') if forward else ("member_id", '%"eaters"%')
    rows = bind.exec_driver_sql(
        "SELECT id, undo_data FROM change WHERE undo_data LIKE ? OR undo_data LIKE ?",
        (f"%{words[0]}%", words[1]),
    ).fetchall()
    for change_id, raw in rows:
        data = json.loads(raw) if isinstance(raw, str) else raw
        new = _rename(data, forward)
        if new != data:
            bind.exec_driver_sql(
                "UPDATE change SET undo_data = ? WHERE id = ?", (json.dumps(new), change_id)
            )


def upgrade() -> None:
    op.create_table(
        "member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("colour", sa.String(length=20), nullable=True),
        sa.Column("portion_quarters", sa.Integer(), server_default="4", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_name", sa.String(length=100), server_default="", nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "portion_quarters >= 1 AND portion_quarters <= 8",
            name=op.f("ck_member_portion_range"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_member_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("member", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_member_household_id"), ["household_id"])
    # Each login gets its own person, numbered the same.
    op.execute(
        "INSERT INTO member (id, household_id, name, portion_quarters, created_at,"
        " created_by_name) SELECT id, household_id, name, 4, created_at, '' FROM login"
    )

    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.add_column(sa.Column("member_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("shared", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.create_unique_constraint(batch_op.f("uq_login_member_id"), ["member_id"])
        batch_op.create_foreign_key(
            batch_op.f("fk_login_member_id_member"),
            "member",
            ["member_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute("UPDATE login SET member_id = id")

    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("member_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_session_member_id_member"),
            "member",
            ["member_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.add_column(sa.Column("member_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_change_member_id_member"),
            "member",
            ["member_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        "UPDATE change SET member_id = login_id"
        " WHERE login_id IS NOT NULL AND login_id IN (SELECT id FROM member)"
    )

    with op.batch_alter_table("tub", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("member_id", sa.Integer(), nullable=True))
    op.execute("UPDATE tub SET member_id = member_login_id")
    with op.batch_alter_table("tub", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint("fk_tub_member_login_id_login", type_="foreignkey")
        batch_op.drop_column("member_login_id")
        batch_op.create_foreign_key(
            batch_op.f("fk_tub_member_id_member"),
            "member",
            ["member_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("meal_eater", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("member_id", sa.Integer(), nullable=True))
    op.execute("UPDATE meal_eater SET member_id = login_id")
    with op.batch_alter_table("meal_eater", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint("uq_meal_eater_meal_id_login_id", type_="unique")
        batch_op.drop_constraint("fk_meal_eater_login_id_login", type_="foreignkey")
        batch_op.drop_index("ix_meal_eater_login_id")
        batch_op.drop_column("login_id")
        batch_op.alter_column("member_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f("ix_meal_eater_member_id"), ["member_id"])
        batch_op.create_unique_constraint(
            "uq_meal_eater_meal_id_member_id", ["meal_id", "member_id"]
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_meal_eater_member_id_member"),
            "member",
            ["member_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_table(
        "join_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_join_link_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"],
            ["login.id"],
            name=op.f("fk_join_link_login_id_login"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_join_link")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_join_link_token_hash")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("join_link", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_join_link_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_join_link_login_id"), ["login_id"])

    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("ask_whos_this", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )

    _rewrite_undo_records(forward=True)


def downgrade() -> None:
    _rewrite_undo_records(forward=False)

    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("ask_whos_this")

    op.drop_table("join_link")

    # Back on the logins: the login each person has (none: the row or the link goes).
    with op.batch_alter_table("meal_eater", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("login_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE meal_eater SET login_id ="
        " (SELECT login.id FROM login WHERE login.member_id = meal_eater.member_id)"
    )
    op.execute("DELETE FROM meal_eater WHERE login_id IS NULL")
    with op.batch_alter_table("meal_eater", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint("uq_meal_eater_meal_id_member_id", type_="unique")
        batch_op.drop_constraint("fk_meal_eater_member_id_member", type_="foreignkey")
        batch_op.drop_index("ix_meal_eater_member_id")
        batch_op.drop_column("member_id")
        batch_op.alter_column("login_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index("ix_meal_eater_login_id", ["login_id"])
        batch_op.create_unique_constraint("uq_meal_eater_meal_id_login_id", ["meal_id", "login_id"])
        batch_op.create_foreign_key(
            "fk_meal_eater_login_id_login", "login", ["login_id"], ["id"], ondelete="CASCADE"
        )

    with op.batch_alter_table("tub", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("member_login_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE tub SET member_login_id ="
        " (SELECT login.id FROM login WHERE login.member_id = tub.member_id)"
    )
    with op.batch_alter_table("tub", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint("fk_tub_member_id_member", type_="foreignkey")
        batch_op.drop_column("member_id")
        batch_op.create_foreign_key(
            "fk_tub_member_login_id_login",
            "login",
            ["member_login_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.drop_constraint("fk_change_member_id_member", type_="foreignkey")
        batch_op.drop_column("member_id")

    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_constraint("fk_session_member_id_member", type_="foreignkey")
        batch_op.drop_column("member_id")

    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.drop_constraint("fk_login_member_id_member", type_="foreignkey")
        batch_op.drop_constraint("uq_login_member_id", type_="unique")
        batch_op.drop_column("shared")
        batch_op.drop_column("member_id")

    op.drop_table("member")
