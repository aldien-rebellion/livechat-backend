"""Grant or revoke global administration using an operator's database access.

Run after migrations: python -m scripts.set_admin person@example.com --grant
"""
import argparse
import asyncio

from sqlalchemy import select

from app.db.session import async_session_maker, engine
from app.models.user import User


async def set_admin(email: str, grant: bool) -> None:
    try:
        async with async_session_maker() as db:
            user = await db.scalar(select(User).where(User.email == email.strip().lower()))
            if user is None:
                raise SystemExit("No registered user has that email address.")
            user.is_admin = grant
            await db.commit()
            print(f"Administrator privilege {'granted to' if grant else 'revoked from'} {user.email}.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage explicit global administrators.")
    parser.add_argument("email")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--grant", action="store_true")
    action.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    asyncio.run(set_admin(args.email, args.grant))


if __name__ == "__main__":
    main()
