import hashlib
import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.base import Base
from db.dal import qr_login_dal
from db.models import QrLoginRequest, User

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
CHROME_ON_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"


class QrLoginDalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            session.add_all([User(user_id=42), User(user_id=43)])
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _start(self, now=NOW):
        async with self.factory() as session:
            started = await qr_login_dal.start_request(
                session, now=now, requester_ip="203.0.113.5", requester_user_agent=CHROME_ON_WINDOWS
            )
            await session.commit()
        return started

    async def _call(self, fn, *args, **kwargs):
        async with self.factory() as session:
            result = await fn(session, *args, **kwargs)
            await session.commit()
        return result

    async def test_the_code_is_stored_only_as_a_digest(self):
        started = await self._start()
        async with self.factory() as session:
            record = (await session.execute(select(QrLoginRequest))).scalar_one()
        self.assertTrue(qr_login_dal.is_token(started.code))
        self.assertEqual(record.code_hash, hashlib.sha256(started.code.encode()).hexdigest())
        self.assertNotIn(started.code, {record.request_id, record.code_hash})
        self.assertTrue(10 <= record.match_number <= 99)

    async def test_full_flow_hands_the_session_over_exactly_once(self):
        started = await self._start()
        rid = started.request_id
        self.assertEqual(
            (await self._call(qr_login_dal.poll_request, rid, now=NOW)).status, "pending"
        )

        claim = await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=NOW)
        self.assertIsNone(claim.error)
        polled = await self._call(qr_login_dal.poll_request, rid, now=NOW)
        self.assertEqual(polled.status, "scanned")
        number = polled.match_number
        assert number is not None

        wrong = await self._call(
            qr_login_dal.approve_request, rid, user_id=42, number=(number + 1) % 100, now=NOW
        )
        self.assertEqual((wrong.outcome, wrong.attempts_left), ("wrong_number", 2))
        right = await self._call(
            qr_login_dal.approve_request, rid, user_id=42, number=number, now=NOW
        )
        self.assertEqual(right.outcome, "approved")

        collected = await self._call(qr_login_dal.poll_request, rid, now=NOW)
        self.assertEqual((collected.status, collected.user_id), ("approved", 42))
        again = await self._call(qr_login_dal.poll_request, rid, now=NOW)
        self.assertEqual((again.status, again.user_id), ("expired", None))

    async def test_a_claimed_code_belongs_to_the_account_that_scanned_it(self):
        started = await self._start()
        await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=NOW)

        other = await self._call(qr_login_dal.claim_request, started.code, user_id=43, now=NOW)
        self.assertEqual(other.error, "already_claimed")
        same = await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=NOW)
        self.assertIsNone(same.error)

        number = (
            await self._call(qr_login_dal.poll_request, started.request_id, now=NOW)
        ).match_number
        assert number is not None
        stranger = await self._call(
            qr_login_dal.approve_request, started.request_id, user_id=43, number=number, now=NOW
        )
        self.assertEqual(stranger.outcome, "not_found")
        self.assertFalse(
            await self._call(qr_login_dal.deny_request, started.request_id, user_id=43, now=NOW)
        )

    async def test_three_wrong_numbers_deny_the_request(self):
        started = await self._start()
        await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=NOW)
        number = (
            await self._call(qr_login_dal.poll_request, started.request_id, now=NOW)
        ).match_number
        assert number is not None
        outcomes = [
            (
                await self._call(
                    qr_login_dal.approve_request,
                    started.request_id,
                    user_id=42,
                    number=(number + offset) % 100,
                    now=NOW,
                )
            ).outcome
            for offset in (1, 2, 3)
        ]
        self.assertEqual(outcomes, ["wrong_number", "wrong_number", "denied"])
        late = await self._call(
            qr_login_dal.approve_request, started.request_id, user_id=42, number=number, now=NOW
        )
        self.assertEqual(late.outcome, "not_found")
        polled = await self._call(qr_login_dal.poll_request, started.request_id, now=NOW)
        self.assertEqual(polled.status, "denied")

    async def test_an_expired_code_cannot_be_claimed(self):
        started = await self._start()
        later = NOW + timedelta(seconds=qr_login_dal.CODE_TTL_SECONDS + 1)
        claim = await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=later)
        self.assertEqual(claim.error, "not_found")
        polled = await self._call(qr_login_dal.poll_request, started.request_id, now=later)
        self.assertEqual(polled.status, "expired")

    async def test_approval_leaves_the_waiting_browser_time_to_collect(self):
        started = await self._start()
        claimed_at = NOW + timedelta(seconds=100)
        await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=claimed_at)
        number = (
            await self._call(qr_login_dal.poll_request, started.request_id, now=claimed_at)
        ).match_number
        assert number is not None
        approved_at = claimed_at + timedelta(seconds=qr_login_dal.APPROVAL_TTL_SECONDS - 5)
        result = await self._call(
            qr_login_dal.approve_request,
            started.request_id,
            user_id=42,
            number=number,
            now=approved_at,
        )
        self.assertEqual(result.outcome, "approved")
        collected = await self._call(
            qr_login_dal.poll_request, started.request_id, now=approved_at + timedelta(seconds=30)
        )
        self.assertEqual(collected.status, "approved")

    async def test_cancel_and_purge(self):
        started = await self._start()
        await self._call(qr_login_dal.cancel_request, started.request_id, now=NOW)
        polled = await self._call(qr_login_dal.poll_request, started.request_id, now=NOW)
        self.assertEqual(polled.status, "expired")
        claim = await self._call(qr_login_dal.claim_request, started.code, user_id=42, now=NOW)
        self.assertEqual(claim.error, "not_found")

        await self._start(now=NOW + timedelta(seconds=qr_login_dal.RETENTION_SECONDS + 600))
        async with self.factory() as session:
            ids = (await session.execute(select(QrLoginRequest.request_id))).scalars().all()
        self.assertNotIn(started.request_id, ids)
        self.assertEqual(len(ids), 1)
