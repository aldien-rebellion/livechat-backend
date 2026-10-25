
"""Add search vector to messages."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# เปลี่ยนค่านี้ให้ตรงกับ revision ID ของไฟล์นี้
revision = "5e5c0f5bd663"
down_revision = "72ceb50468d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            nullable=True,
        ),
    )

    # สร้าง search_vector สำหรับข้อความที่มีอยู่แล้ว
    op.execute("""
        UPDATE messages
        SET search_vector = to_tsvector('simple', coalesce(content, ''))
    """)

    # ฟังก์ชันอัปเดต search_vector เมื่อเพิ่มหรือแก้ไขข้อความ
    op.execute("""
        CREATE FUNCTION messages_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                to_tsvector('simple', coalesce(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # เรียกฟังก์ชันก่อนบันทึก INSERT หรือ UPDATE
    op.execute("""
        CREATE TRIGGER messages_search_vector_trigger
        BEFORE INSERT OR UPDATE OF content
        ON messages
        FOR EACH ROW
        EXECUTE FUNCTION messages_search_vector_update();
    """)

    # เพิ่ม GIN index เพื่อช่วยให้ค้นหาข้อความได้เร็วขึ้น
    op.create_index(
        "ix_messages_search_vector",
        "messages",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_search_vector",
        table_name="messages",
    )

    op.execute("""
        DROP TRIGGER IF EXISTS messages_search_vector_trigger
        ON messages
    """)

    op.execute("""
        DROP FUNCTION IF EXISTS messages_search_vector_update()
    """)

    op.drop_column("messages", "search_vector")
