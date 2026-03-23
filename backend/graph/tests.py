import os
import tempfile
from urllib.parse import quote
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .registry import register_graph_export


class GraphApiTests(TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = os.path.join(self.temp_dir.name, "graph_registry.json")
        self.registry_patch = patch.dict(os.environ, {"GRAPH_REGISTRY_PATH": self.registry_path})
        self.registry_patch.start()

    def tearDown(self):
        self.registry_patch.stop()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_graph_summary_endpoint_returns_counts(self):
        response = self.client.get("/api/v1/graph/summary/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["entity_node_count"], 0)
        self.assertIn("entity_type_breakdown", payload)
        self.assertIn("top_entities", payload)
        self.assertIn("graph_version", payload)

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

    def test_graph_registry_endpoint_returns_active_version(self):
        record = register_graph_export(
            {
                "run_name": "graph-accepted-v1",
                "input_path": "D:/code/python/challenge/data/processed/annotation/accepted_candidates.jsonl",
                "output_dir": "D:/code/python/challenge/data/processed/graph-accepted-v1",
                "source_type": "accepted_reviewed",
                "stats": {"entity_node_count": 200},
            },
            activate=True,
        )

        response = self.client.get("/api/v1/graph/registry/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active"]["id"], record["id"])
        self.assertGreaterEqual(len(payload["versions"]), 1)

    def test_graph_registry_activate_switches_active_version(self):
        first = register_graph_export(
            {
                "run_name": "graph-silver-v1",
                "input_path": "D:/code/python/challenge/data/annotation/cleaned_silver_corpus.jsonl",
                "output_dir": "D:/code/python/challenge/data/processed/graph-silver-v1",
                "source_type": "cleaned_silver",
                "stats": {"entity_node_count": 175},
            },
            activate=True,
        )
        second = register_graph_export(
            {
                "run_name": "graph-accepted-v1",
                "input_path": "D:/code/python/challenge/data/processed/annotation/accepted_candidates.jsonl",
                "output_dir": "D:/code/python/challenge/data/processed/graph-accepted-v1",
                "source_type": "accepted_reviewed",
                "stats": {"entity_node_count": 210},
            },
            activate=False,
        )

        response = self.client.post("/api/v1/graph/registry/activate/", {"graph_id": second["id"]}, format="json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["record"]["id"], second["id"])
        self.assertEqual(payload["registry"]["active"]["id"], second["id"])
        self.assertNotEqual(first["id"], second["id"])

    def test_reviewed_graph_refresh_rejects_invalid_statuses(self):
        response = self.client.post("/api/v1/graph/datasets/reviewed/refresh/", {"statuses": "accepted"}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_reviewed_graph_refresh_endpoint_returns_summary(self):
        with patch("graph.views.run_reviewed_graph_refresh") as refresh_mock:
            refresh_mock.return_value = {
                "summary": {"stats": {"input_record_count": 9}},
                "registry": {"active": {"id": "graph-1"}},
                "graph_summary": {"entity_node_count": 20},
            }

            response = self.client.post(
                "/api/v1/graph/datasets/reviewed/refresh/",
                {"statuses": ["accepted"], "limit": 10},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["stats"]["input_record_count"], 9)
        refresh_mock.assert_called_once_with(statuses=["accepted"], limit=10)
