"""Re-run the Canvas sync for every connected user, then report resource nesting.

Same code path as the "Sync now" button. Used after migration 0025 so that
resources imported by earlier syncs get adopted by the page they came from
instead of sitting flat in the course list.
"""

from redis import Redis
from sqlalchemy import select

import app.db.base  # noqa: F401  # registers every model before mappers configure
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.integration_credential import IntegrationCredential
from app.models.resource import Resource
from app.models.user import User
from app.services import canvas_sync as canvas_sync_service


def report(db, label: str) -> None:
    rows = db.execute(select(Resource)).scalars().all()
    top = [r for r in rows if r.parent_resource_id is None]
    print(f"{label}: total={len(rows)} top_level={len(top)} nested={len(rows) - len(top)}")
    by_module: dict[str, int] = {}
    for r in top:
        name = (r.metadata_json or {}).get("canvas_module_name") or "(none)"
        by_module[name] = by_module.get(name, 0) + 1
    for name, count in sorted(by_module.items(), key=lambda kv: -kv[1])[:10]:
        print(f"   {count:3d}  {name}")


def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    db = create_session_factory(create_db_engine(settings.database_url))()
    try:
        report(db, "before")
        creds = (
            db.execute(
                select(IntegrationCredential).where(IntegrationCredential.provider == "canvas")
            )
            .scalars()
            .all()
        )
        print(f"canvas credentials: {len(creds)}")
        for cred in creds:
            user = db.execute(select(User).where(User.id == cred.user_id)).scalars().first()
            if user is None:
                continue
            result = canvas_sync_service.sync_canvas(db, user=user, redis=redis)
            db.commit()
            print(f"synced {user.email}: {result}")
        report(db, "after")
    finally:
        db.close()


if __name__ == "__main__":
    main()
