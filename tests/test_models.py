from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.channel import Channel
from app.models.message import Message


def test_user_model_attributes():
    user = User(
        email="test_schema@example.com",
        username="schema_user",
        hashed_password="hashed_sample",
    )
    assert user.__tablename__ == "users"
    assert user.email == "test_schema@example.com"
    assert user.username == "schema_user"
    assert user.hashed_password == "hashed_sample"


def test_workspace_model_attributes():
    ws = Workspace(
        name="Engineering Hub",
        created_by=42,
    )
    assert ws.__tablename__ == "workspaces"
    assert ws.name == "Engineering Hub"
    assert ws.created_by == 42


def test_workspace_member_model_attributes():
    member = WorkspaceMember(
        workspace_id=1,
        user_id=42,
        role="admin",
    )
    assert member.__tablename__ == "workspace_members"
    assert member.workspace_id == 1
    assert member.user_id == 42
    assert member.role == "admin"


def test_channel_model_attributes():
    channel = Channel(
        workspace_id=1,
        name="dev-chat",
    )
    assert channel.__tablename__ == "channels"
    assert channel.workspace_id == 1
    assert channel.name == "dev-chat"


def test_message_model_attributes():
    msg = Message(
        workspace_id=1,
        channel_id=10,
        user_id=42,
        content="Testing message ORM schema",
    )
    assert msg.__tablename__ == "messages"
    assert msg.workspace_id == 1
    assert msg.channel_id == 10
    assert msg.user_id == 42
    assert msg.content == "Testing message ORM schema"
    assert hasattr(msg, "search_vector")
