"""Add device FCM tokens

Revision ID: 2d5a78c1f3b4
Revises: 11f62a49b9d7
Create Date: 2026-11-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2d5a78c1f3b4"
down_revision = "11f62a49b9d7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fcm_token", sa.String(length=4096), nullable=True))


def downgrade():
    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.drop_column("fcm_token")
