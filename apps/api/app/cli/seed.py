from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import base  # noqa: F401  # ensure all model classes are registered before mapper config
from app.db.session import create_db_engine, create_session_factory
from app.models.course import Course
from app.models.notebook import Notebook
from app.models.resource import Resource
from app.models.task import Task
from app.models.user import User
from app.services.auth_passwords import hash_password


def _seed_password() -> str | None:
    raw = (os.getenv("SEED_DEV_PASSWORD") or "").strip()
    return raw or None


def ensure_dev_user(db: Session) -> User:
    password = _seed_password()
    user = db.execute(select(User).where(User.email == "dev@example.com")).scalars().first()
    if user:
        # Local/demo: set a password when SEED_DEV_PASSWORD is provided and none exists yet.
        if password and not user.password_hash:
            user.password_hash = hash_password(password)
            db.add(user)
            db.commit()
            db.refresh(user)
            print("Claimed seed user password from SEED_DEV_PASSWORD (dev@example.com).")
        elif not user.password_hash:
            print(
                "Seed user exists without a password — use Create account on /login "
                "with email dev@example.com, or set SEED_DEV_PASSWORD and re-run seed."
            )
        return user
    user = User(
        email="dev@example.com",
        name="Dev User",
        password_hash=hash_password(password) if password else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if password:
        print("Created seed user dev@example.com with SEED_DEV_PASSWORD.")
    else:
        print(
            "Created seed user without password — claim via Create account on /login, "
            "or set SEED_DEV_PASSWORD and re-run seed."
        )
    return user


def seed() -> None:
    settings = get_settings()
    engine = create_db_engine(os.getenv("DATABASE_URL", settings.database_url))
    SessionLocal = create_session_factory(engine)

    db = SessionLocal()
    try:
        user = ensure_dev_user(db)

        # Courses
        if db.execute(select(Course).where(Course.user_id == user.id)).scalars().first() is None:
            course1 = Course(user_id=user.id, name="CS 101", code="CS101", term="Spring 2026", color="#3b82f6")
            course2 = Course(user_id=user.id, name="MATH 201", code="MATH201", term="Spring 2026", color="#22c55e")
            db.add_all([course1, course2])
            db.commit()
            db.refresh(course1)
            db.refresh(course2)

            # Tasks
            db.add_all(
                [
                    Task(user_id=user.id, course_id=course1.id, title="Problem Set 1", status="todo", estimated_minutes=120),
                    Task(user_id=user.id, course_id=course1.id, title="Read Chapter 2", status="todo", estimated_minutes=60),
                    Task(user_id=user.id, course_id=course2.id, title="Quiz 1 Study", status="todo", estimated_minutes=90),
                ]
            )

            # Resources (metadata only for now)
            db.add_all(
                [
                    Resource(user_id=user.id, course_id=course1.id, title="Syllabus", resource_type="pdf"),
                    Resource(user_id=user.id, course_id=course2.id, title="Lecture 1 Slides", resource_type="pdf"),
                ]
            )

            # Notebooks
            db.add_all(
                [
                    Notebook(user_id=user.id, course_id=course1.id, title="CS 101 Notes"),
                    Notebook(user_id=user.id, course_id=course2.id, title="MATH 201 Notes"),
                ]
            )

            db.commit()

        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

