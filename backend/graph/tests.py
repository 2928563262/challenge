from urllib.parse import quote

from django.test import TestCase
from rest_framework.test import APIClient


class GraphApiTests(TestCase):
    client_class = APIClient

    def test_graph_summary_endpoint_returns_counts(self):
        response = self.client.get("/api/v1/graph/summary/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["entity_node_count"], 0)
        self.assertIn("entity_type_breakdown", payload)
        self.assertIn("top_entities", payload)

    def test_graph_showcase_endpoint_returns_cases(self):
        response = self.client.get("/api/v1/graph/showcase/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("cases", payload)
        self.assertGreater(len(payload["cases"]), 0)
        self.assertIn("entity", payload["cases"][0])

    def test_graph_entity_search_supports_keyword_and_type(self):
        response = self.client.get(
            "/api/v1/graph/entities/",
            {"keyword": "桂枝", "entity_type": "FORMULA", "limit": 5},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["total"], 0)
        self.assertLessEqual(len(payload["results"]), 5)
        self.assertTrue(all(item["entity_type"] == "FORMULA" for item in payload["results"]))

    def test_graph_entity_detail_returns_relations_and_mentions(self):
        search_response = self.client.get(
            "/api/v1/graph/entities/",
            {"keyword": "桂枝", "entity_type": "FORMULA", "limit": 1},
        )
        entity_id = search_response.json()["results"][0]["entity_id"]

        response = self.client.get(f"/api/v1/graph/entities/{quote(entity_id, safe='')}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entity"]["entity_id"], entity_id)
        self.assertIn("mentions", payload)
        self.assertIn("stats", payload)

    def test_graph_entity_detail_returns_404_for_unknown_entity(self):
        response = self.client.get("/api/v1/graph/entities/UNKNOWN%7CENTITY/")

        self.assertEqual(response.status_code, 404)
