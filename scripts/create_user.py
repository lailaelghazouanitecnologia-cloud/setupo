"""
One-off script to create a user account.
Usage: python -m scripts.create_user
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.core import db
from server.core.users import create_user


async def main():
    await db.init_db()
    try:
        user = await create_user(
            email="miuser@hotmail.com",
            password="bakemonoko",
            name="miuser",
        )
        # Mark as verified
        await db.update("users", user["id"], {"verified": 1})
        print(f"User created: {user['email']} (id={user['id']}, verified=True)")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
