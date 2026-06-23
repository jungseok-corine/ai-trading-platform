"""C-5.23: 계좌 목록 API(자동매매 account_id 드롭다운 선택용)."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def test_list_accounts(db_session: AsyncSession) -> None:
    db_session.add(Account(account_type=AccountType.PAPER, broker_account_no="50000000-01",
                           alias="모의1"))
    db_session.add(Account(account_type=AccountType.LIVE, broker_account_no="60000000-01"))
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/account/list")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        paper = next(a for a in data if a["account_type"] == "paper")
        assert paper["alias"] == "모의1"
        assert paper["broker_account_no"] == "50000000-01"
        assert "id" in paper
    finally:
        app.dependency_overrides.clear()
