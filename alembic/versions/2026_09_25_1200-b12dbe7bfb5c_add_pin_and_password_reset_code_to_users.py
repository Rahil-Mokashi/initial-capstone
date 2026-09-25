"""add pin and password reset code fields to users

Revision ID: b12dbe7bfb5c
Revises: e7a2c19f4b6d
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b12dbe7bfb5c'
down_revision: Union[str, Sequence[str], None] = 'e7a2c19f4b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    All four columns are nullable with no server default - every
    existing user simply has no PIN and no pending reset code until
    they (or an administrator) set one, which is the correct state for
    a row that predates these features rather than a value that needs
    backfilling.
    """
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pin_hash', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('pin_set_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('password_reset_code_hash', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('password_reset_code_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_reset_code_expires_at')
        batch_op.drop_column('password_reset_code_hash')
        batch_op.drop_column('pin_set_at')
        batch_op.drop_column('pin_hash')
