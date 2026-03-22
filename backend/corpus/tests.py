from django.test import TestCase
from rest_framework.test import APIClient


class CorpusApiTests(TestCase):
    client_class = APIClient

    def test_overview_endpoint_returns_summary(self):
        response = self.client.get("/api/v1/corpus/overview/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("stats", payload)
        self.assertGreater(payload["stats"]["entry_count"], 0)

    def test_search_endpoint_requires_keyword(self):
        response = self.client.get("/api/v1/corpus/search/")

        self.assertEqual(response.status_code, 400)

    def test_search_endpoint_returns_matches(self):
        response = self.client.get("/api/v1/corpus/search/", {"keyword": "桂枝汤"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["keyword"], "桂枝汤")
        self.assertGreater(payload["total"], 0)
