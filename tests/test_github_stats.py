import unittest
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from activity import DAYS, render_activity
from github_stats import GitHubAPIError, Queries, Stats
import generate_images


class QueryTests(unittest.IsolatedAsyncioTestCase):
    def make_queries(self, status, payload):
        response = unittest.mock.Mock(status=status)
        response.json = AsyncMock(return_value=payload)
        session = unittest.mock.Mock()
        session.post = AsyncMock(return_value=response)
        return Queries("IceCokei", "test-placeholder", session)

    async def test_rejected_token_cannot_become_zero_statistics(self):
        queries = self.make_queries(401, {"message": "Bad credentials"})
        with self.assertRaises(GitHubAPIError) as error:
            await queries.query("query { viewer { login } }")
        self.assertTrue(error.exception.authentication_failed)

    async def test_graphql_errors_fail_even_with_partial_data(self):
        queries = self.make_queries(200, {
            "data": {"viewer": {"login": "IceCokei"}},
            "errors": [{"type": "RATE_LIMITED", "message": "private details"}],
        })
        with self.assertRaises(GitHubAPIError) as error:
            await queries.query("query { viewer { login } }")
        self.assertNotIn("private details", str(error.exception))
        self.assertFalse(error.exception.authentication_failed)

    async def test_valid_data_is_preserved(self):
        payload = {"data": {"viewer": {"login": "IceCokei"}}}
        self.assertEqual(await self.make_queries(200, payload).query("query"), payload)

    async def test_missing_user_cannot_generate_no_name_card(self):
        stats = Stats("IceCokei", "test-placeholder", None)
        stats.queries.query = AsyncMock(return_value={"data": {"viewer": None}})
        with self.assertRaises(RuntimeError):
            await stats.get_stats()

    async def test_zero_activity_for_real_user_remains_valid(self):
        stats = Stats("IceCokei", "test-placeholder", None)
        stats.queries.query = AsyncMock(return_value={"data": {"viewer": {
            "name": None, "login": "IceCokei", "repositories": {"nodes": []},
            "repositoriesContributedTo": {"nodes": []},
        }}})
        await stats.get_stats()
        self.assertEqual(await stats.name, "IceCokei")
        self.assertEqual(await stats.stargazers, 0)

    async def test_inaccessible_traffic_is_not_reported_as_zero(self):
        stats = Stats("IceCokei", "test-placeholder", None)
        stats._repos = {"IceCokei/IceCokei"}
        stats.queries.query_rest = AsyncMock(return_value={"message": "Forbidden"})
        self.assertIsNone(await stats.views)

    async def test_account_is_explicit_in_every_statistics_query(self):
        for query in (Queries.repos_overview("IceCokei"),
                      Queries.contrib_years("IceCokei"),
                      Queries.all_contribs(["2026"], "IceCokei")):
            self.assertIn('viewer: user(login: "IceCokei")', query)

    async def test_authentication_fallback_preloads_owner_before_rendering(self):
        original = unittest.mock.Mock()
        original.get_stats = AsyncMock(side_effect=GitHubAPIError(401, True))
        fallback = unittest.mock.Mock()
        fallback.get_stats = AsyncMock()
        with patch.dict("os.environ", {
            "ACCESS_TOKEN": "invalid-placeholder", "GITHUB_TOKEN": "fallback-placeholder",
            "GITHUB_REPOSITORY_OWNER": "IceCokei", "GITHUB_ACTOR": "github-actions[bot]",
        }, clear=True), patch.object(generate_images, "Stats", side_effect=[original, fallback]) as factory, \
                patch.object(generate_images, "generate_overview", new_callable=AsyncMock) as overview, \
                patch.object(generate_images, "generate_languages", new_callable=AsyncMock), \
                patch.object(generate_images, "generate_activity", new_callable=AsyncMock):
            await generate_images.main()
        self.assertEqual(factory.call_args_list[1].args[:2],
                         ("IceCokei", "fallback-placeholder"))
        fallback.get_stats.assert_awaited_once()
        overview.assert_awaited_once_with(fallback)

    async def test_schema_errors_do_not_trigger_authentication_fallback(self):
        stats = unittest.mock.Mock()
        stats.get_stats = AsyncMock(side_effect=GitHubAPIError(200))
        with patch.dict("os.environ", {
            "ACCESS_TOKEN": "test-placeholder", "GITHUB_TOKEN": "fallback-placeholder",
            "GITHUB_REPOSITORY_OWNER": "IceCokei",
        }, clear=True), patch.object(generate_images, "Stats", return_value=stats) as factory:
            with self.assertRaises(GitHubAPIError):
                await generate_images.main()
        factory.assert_called_once()


class ActivityTests(unittest.TestCase):
    def days(self, count=0):
        return [{"date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
                 "contributionCount": count} for index in range(DAYS)]

    def test_empty_activity_still_renders_31_data_points_in_both_themes(self):
        for dark in (False, True):
            root = ET.fromstring(render_activity("IceCokei", self.days(), dark))
            self.assertEqual(len(root.findall(".//{*}circle")), DAYS)
            self.assertIn("0 contributions", " ".join(root.itertext()))

    def test_counts_and_user_text_survive_xml_rendering(self):
        root = ET.fromstring(render_activity("A & B", self.days(3)))
        self.assertIn("93 contributions", " ".join(root.itertext()))
        self.assertIn("A & B", " ".join(root.itertext()))

    def test_incomplete_or_invalid_calendar_is_rejected(self):
        for days in (self.days()[:-1], self.days(-1)):
            with self.assertRaises(ValueError):
                render_activity("IceCokei", days)


if __name__ == "__main__":
    unittest.main()
