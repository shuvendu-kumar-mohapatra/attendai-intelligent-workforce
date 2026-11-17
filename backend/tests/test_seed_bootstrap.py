import pytest
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.database import Base
from app.core.init_seed import seed_database_if_empty
from app.models.models import User
from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_auto_seed_on_empty_db(tmp_path):
    db_file = tmp_path / "test_bootstrap.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    # 1. Run seed on empty DB
    async with TestSession() as session:
        seeded = await seed_database_if_empty(session)
        assert seeded is True
        
        # Verify 3 demo users
        users = (await session.execute(select(User))).scalars().all()
        user_emails = {u.email for u in users}
        assert "admin@attendai.com" in user_emails
        assert "hrmanager@attendai.com" in user_emails
        assert "employee@attendai.com" in user_emails
        
    # 2. Run seed again on non-empty DB -> should skip
    async with TestSession() as session:
        seeded_again = await seed_database_if_empty(session)
        assert seeded_again is False

    await test_engine.dispose()
