"""Keep directory deletion tombstones after purging chat content."""
from alembic import op
import sqlalchemy as sa

revision = "a26f10dirs01"
down_revision = "a26f10auth01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("channels", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "deleted_at")
    op.drop_column("workspaces", "deleted_at")
