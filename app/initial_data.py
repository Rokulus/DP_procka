"""
Put here any Python code that must be runned before application startup.
It is included in `init.sh` script.

By defualt `main` create a superuser if not exists
"""

import asyncio
import os

from sqlalchemy import select

from app.core import config, security
from app.core.session import async_session
from app.models import User

from pathlib import Path

async def main() -> None:
    print("Start initial data")
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.email == config.settings.FIRST_SUPERUSER_EMAIL)
        )
        user = result.scalars().first()

        if user is None:
            new_superuser = User(
                email=config.settings.FIRST_SUPERUSER_EMAIL,
                hashed_password=security.get_password_hash(
                    config.settings.FIRST_SUPERUSER_PASSWORD
                ),
                is_superuser=True
            )
            session.add(new_superuser)
            await session.commit()

            PROJECT_DIR = Path(__file__).parent.parent.parent.parent
            name_of_user_directory = user.id
            path = f"{PROJECT_DIR}/uploaded_fmu_files/{name_of_user_directory}"
            os.mkdir(path)

            path = f"{PROJECT_DIR}/uploaded_matlab_files/{name_of_user_directory}"
            os.mkdir(path)

            path = f"{PROJECT_DIR}/static/assets/models/{name_of_user_directory}"
            os.mkdir(path)

            path = f"{PROJECT_DIR}/static/assets/models_xml/{name_of_user_directory}"
            os.mkdir(path)

            print("Superuser was created")
        else:
            print("Superuser already exists in database")

        print("Initial data created")


if __name__ == "__main__":
    asyncio.run(main())
