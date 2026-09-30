from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from db.dal import device_name_dal


def _sql(statement) -> str:
    return " ".join(
        str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        ).split()
    )


class DeviceNameDalTests(IsolatedAsyncioTestCase):
    def _session(self, rows=()):
        result = MagicMock()
        result.all.return_value = list(rows)
        return SimpleNamespace(execute=AsyncMock(return_value=result))

    async def test_get_device_names_maps_tokens_to_names(self):
        session = self._session([("token-a", "Work laptop"), ("token-b", "Mom's phone")])

        names = await device_name_dal.get_device_names(session, 42)

        self.assertEqual(names, {"token-a": "Work laptop", "token-b": "Mom's phone"})
        sql = _sql(session.execute.await_args.args[0])
        self.assertIn("WHERE user_device_names.user_id = 42", sql)

    async def test_set_device_name_upserts_on_the_user_and_token(self):
        session = self._session()

        await device_name_dal.set_device_name(session, 42, "token-a", "Work laptop")

        sql = _sql(session.execute.await_args.args[0])
        self.assertTrue(sql.startswith("INSERT INTO user_device_names"), sql)
        self.assertIn("ON CONFLICT (user_id, device_token) DO UPDATE SET", sql)
        self.assertIn("name = excluded.name", sql)
        self.assertIn("updated_at = excluded.updated_at", sql)

    async def test_empty_name_deletes_only_that_label(self):
        session = self._session()

        await device_name_dal.set_device_name(session, 42, "token-a", "")

        sql = _sql(session.execute.await_args.args[0])
        self.assertTrue(sql.startswith("DELETE FROM user_device_names"), sql)
        self.assertIn("user_device_names.user_id = 42", sql)
        self.assertIn("user_device_names.device_token = 'token-a'", sql)

    async def test_merge_drops_source_duplicates_before_moving_the_rest(self):
        session = self._session()

        await device_name_dal.merge_owner(session, 7, 9)

        delete_sql, update_sql = (_sql(call.args[0]) for call in session.execute.await_args_list)
        self.assertTrue(delete_sql.startswith("DELETE FROM user_device_names"), delete_sql)
        self.assertIn("user_device_names.user_id = 7", delete_sql)
        self.assertIn("user_device_names.user_id = 9", delete_sql)
        self.assertTrue(update_sql.startswith("UPDATE user_device_names SET user_id=9"), update_sql)
        self.assertIn("WHERE user_device_names.user_id = 7", update_sql)
