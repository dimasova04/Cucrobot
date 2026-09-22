from database import repo
from database.models import User


async def test_get_or_create_user_is_idempotent(session_factory):
    async with session_factory() as s:
        u1 = await repo.get_or_create_user(s, 42, "alice")
        await s.commit()
    async with session_factory() as s:
        u2 = await repo.get_or_create_user(s, 42, "alice2")
        await s.commit()
    assert u1.id == u2.id == 42
    assert u2.username == "alice2"
    assert u2.crystals == 0
    assert u2.rules_accepted_at is None
