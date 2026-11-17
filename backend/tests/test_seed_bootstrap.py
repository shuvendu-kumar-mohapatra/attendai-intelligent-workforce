import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.database import Base
from app.core.init_seed import seed_database_if_empty
from app.models.models import User, Employee, AttendanceRecord
from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_full_workforce_auto_seed(tmp_path):
    db_file = tmp_path / "test_full_bootstrap.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    # 1. Run seed on empty DB
    async with TestSession() as session:
        seeded = await seed_database_if_empty(session)
        assert seeded is True
        
        # Verify 200 employees
        emp_count = (await session.execute(select(func.count(Employee.id)))).scalar()
        assert emp_count == 200
        
        # Verify attendance records
        att_count = (await session.execute(select(func.count(AttendanceRecord.id)))).scalar()
        assert att_count > 5000
        
        # Verify demo users
        users = (await session.execute(select(User))).scalars().all()
        user_emails = {u.email for u in users}
        assert "admin@attendai.com" in user_emails
        assert "hrmanager@attendai.com" in user_emails
        assert "employee@attendai.com" in user_emails
        
    # 2. Run seed again on populated DB -> should skip
    async with TestSession() as session:
        seeded_again = await seed_database_if_empty(session)
        assert seeded_again is False

    await test_engine.dispose()
