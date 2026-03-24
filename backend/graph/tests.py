import os
import json
import tempfile
from urllib.parse import quote
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .registry import register_graph_export
from .services import load_graph_data, run_neo4j_sync


class GraphApiTests(TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        load_graph_data.cache_clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = os.path.join(self.temp_dir.name, "graph_registry.json")
        self.manual_relations_path = os.path.join(self.temp_dir.name, "manual_relation_overrides.json")
        self.registry_patch = patch.dict(
            os.environ,
            {
                "GRAPH_REGISTRY_PATH": self.registry_path,
                "GRAPH_MANUAL_RELATIONS_PATH": self.manual_relations_path,
            },
        )
        self.registry_patch.start()

    def tearDown(self):
        self.registry_patch.stop()
        load_graph_data.cache_clear()
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

    def test_graph_entity_pathways_returns_candidate_paths(self):
        search_response = self.client.get(
            "/api/v1/graph/entities/",
            {"keyword": "桂枝", "entity_type": "FORMULA", "limit": 1},
        )
        entity_id = search_response.json()["results"][0]["entity_id"]

        response = self.client.get(f"/api/v1/graph/entities/{quote(entity_id, safe='')}/pathways/", {"limit": 10})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entity"]["entity_id"], entity_id)
        self.assertIn("paths", payload)
        self.assertLessEqual(len(payload["paths"]), 10)
        if payload["paths"]:
            self.assertIn("path_type", payload["paths"][0])
            self.assertIn("nodes", payload["paths"][0])

    def test_graph_entity_pathways_rejects_non_integer_limit(self):
        response = self.client.get("/api/v1/graph/entities/UNKNOWN%7CENTITY/pathways/", {"limit": "abc"})

        self.assertEqual(response.status_code, 400)

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
        refresh_mock.assert_called_once_with(statuses=["accepted"], limit=10, sync_neo4j=False)

    def test_reviewed_graph_refresh_supports_optional_neo4j_sync(self):
        with patch("graph.views.run_reviewed_graph_refresh") as refresh_mock:
            refresh_mock.return_value = {
                "summary": {"stats": {"input_record_count": 9}},
                "registry": {"active": {"id": "graph-1"}},
                "graph_summary": {"entity_node_count": 20},
                "neo4j_sync": {"ok": True},
            }

            response = self.client.post(
                "/api/v1/graph/datasets/reviewed/refresh/",
                {"statuses": ["accepted"], "limit": 10, "sync_neo4j": True},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["neo4j_sync"]["ok"])
        refresh_mock.assert_called_once_with(statuses=["accepted"], limit=10, sync_neo4j=True)

    def test_graph_neo4j_sync_endpoint_returns_status(self):
        with patch("graph.views.get_graph_sync_status") as status_mock:
            status_mock.return_value = {"exists": True, "path": "report.json", "report": {"ok": True}}

            response = self.client.get("/api/v1/graph/neo4j/sync/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["exists"])

    def test_graph_neo4j_sync_endpoint_runs_sync(self):
        with patch("graph.views.run_neo4j_sync") as sync_mock, patch("graph.views.get_graph_sync_status") as status_mock:
            sync_mock.return_value = {"ok": True, "summary": {"entity_nodes": 10}}
            status_mock.return_value = {"exists": True, "path": "report.json", "report": {"ok": True}}

            response = self.client.post("/api/v1/graph/neo4j/sync/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["sync"]["ok"])
        sync_mock.assert_called_once_with()

    def test_manual_relation_upsert_endpoint_creates_override(self):
        syndrome_response = self.client.get("/api/v1/graph/entities/", {"keyword": "太阳病", "entity_type": "SYNDROME", "limit": 1})
        formula_response = self.client.get("/api/v1/graph/entities/", {"keyword": "桂枝汤", "entity_type": "FORMULA", "limit": 1})
        syndrome_id = syndrome_response.json()["results"][0]["entity_id"]
        formula_id = formula_response.json()["results"][0]["entity_id"]

        response = self.client.post(
            "/api/v1/graph/manual-relations/",
            {
                "action": "upsert",
                "start_id": syndrome_id,
                "end_id": formula_id,
                "relation_type": "SYNDROME_TO_FORMULA",
                "example_text": "人工补充关系",
                "evidence_count": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["record"]["action"], "upsert")
        list_response = self.client.get("/api/v1/graph/manual-relations/")
        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(list_response.json()["total"], 1)

    def test_manual_relation_suppress_hides_relation_from_detail(self):
        syndrome_response = self.client.get("/api/v1/graph/entities/", {"keyword": "太阳病", "entity_type": "SYNDROME", "limit": 1})
        formula_response = self.client.get("/api/v1/graph/entities/", {"keyword": "桂枝汤", "entity_type": "FORMULA", "limit": 1})
        syndrome_id = syndrome_response.json()["results"][0]["entity_id"]
        formula_id = formula_response.json()["results"][0]["entity_id"]

        before = self.client.get(f"/api/v1/graph/entities/{quote(syndrome_id, safe='')}/").json()
        has_relation_before = any(
            item["relation_type"] == "SYNDROME_TO_FORMULA" and item["related_entity"]["entity_id"] == formula_id
            for item in before["outgoing_relations"]
        )
        self.assertTrue(has_relation_before)

        suppress_response = self.client.post(
            "/api/v1/graph/manual-relations/",
            {
                "action": "suppress",
                "start_id": syndrome_id,
                "end_id": formula_id,
                "relation_type": "SYNDROME_TO_FORMULA",
            },
            format="json",
        )
        self.assertEqual(suppress_response.status_code, 201)

        after = self.client.get(f"/api/v1/graph/entities/{quote(syndrome_id, safe='')}/").json()
        has_relation_after = any(
            item["relation_type"] == "SYNDROME_TO_FORMULA" and item["related_entity"]["entity_id"] == formula_id
            for item in after["outgoing_relations"]
        )
        self.assertFalse(has_relation_after)

    def test_manual_relation_delete_endpoint(self):
        syndrome_response = self.client.get("/api/v1/graph/entities/", {"keyword": "太阳病", "entity_type": "SYNDROME", "limit": 1})
        formula_response = self.client.get("/api/v1/graph/entities/", {"keyword": "桂枝汤", "entity_type": "FORMULA", "limit": 1})
        syndrome_id = syndrome_response.json()["results"][0]["entity_id"]
        formula_id = formula_response.json()["results"][0]["entity_id"]

        create_response = self.client.post(
            "/api/v1/graph/manual-relations/",
            {
                "action": "upsert",
                "start_id": syndrome_id,
                "end_id": formula_id,
                "relation_type": "SYNDROME_TO_FORMULA",
            },
            format="json",
        )
        override_id = create_response.json()["record"]["id"]

        delete_response = self.client.delete(f"/api/v1/graph/manual-relations/{override_id}/")
        self.assertEqual(delete_response.status_code, 200)

    def test_run_neo4j_sync_passes_resolved_manual_overrides(self):
        data = load_graph_data()
        syndrome_id = next(item["entity_id"] for item in data["entities"].values() if item["entity_type"] == "SYNDROME")
        formula_id = next(item["entity_id"] for item in data["entities"].values() if item["entity_type"] == "FORMULA")
        symptom_id = next(item["entity_id"] for item in data["entities"].values() if item["entity_type"] == "SYMPTOM")

        manual_payload = {
            "records": [
                {
                    "id": "manual-old-upsert",
                    "graph_id": "default-graph",
                    "action": "upsert",
                    "relation_type": "SYNDROME_TO_FORMULA",
                    "start_id": syndrome_id,
                    "end_id": formula_id,
                    "evidence_count": 2,
                    "record_ids": [],
                    "example_text": "old",
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:00:00+00:00",
                },
                {
                    "id": "manual-new-suppress",
                    "graph_id": "default-graph",
                    "action": "suppress",
                    "relation_type": "SYNDROME_TO_FORMULA",
                    "start_id": syndrome_id,
                    "end_id": formula_id,
                    "evidence_count": 1,
                    "record_ids": [],
                    "example_text": "suppress",
                    "created_at": "2026-03-24T00:01:00+00:00",
                    "updated_at": "2026-03-24T00:01:00+00:00",
                },
                {
                    "id": "manual-symptom-upsert",
                    "graph_id": "default-graph",
                    "action": "upsert",
                    "relation_type": "SYNDROME_HAS_SYMPTOM",
                    "start_id": syndrome_id,
                    "end_id": symptom_id,
                    "evidence_count": 3,
                    "record_ids": [],
                    "example_text": "symptom",
                    "created_at": "2026-03-24T00:02:00+00:00",
                    "updated_at": "2026-03-24T00:02:00+00:00",
                },
                {
                    "id": "manual-other-graph",
                    "graph_id": "other-graph",
                    "action": "upsert",
                    "relation_type": "SYNDROME_TO_FORMULA",
                    "start_id": syndrome_id,
                    "end_id": formula_id,
                    "evidence_count": 4,
                    "record_ids": [],
                    "example_text": "other",
                    "created_at": "2026-03-24T00:03:00+00:00",
                    "updated_at": "2026-03-24T00:03:00+00:00",
                },
            ]
        }
        with open(self.manual_relations_path, "w", encoding="utf-8") as handle:
            json.dump(manual_payload, handle, ensure_ascii=False, indent=2)

        with (
            patch("scripts.import_graph_to_neo4j.import_graph") as import_mock,
            patch("graph.services._write_neo4j_sync_report"),
        ):
            import_mock.return_value = {
                "entity_nodes": 1,
                "clause_nodes": 1,
                "entity_relations": 1,
                "clause_mentions": 1,
                "manual_overrides": 2,
                "manual_relations_upserted": 1,
                "manual_relations_suppressed": 1,
            }
            payload = run_neo4j_sync()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["manual_overrides"], 2)
        self.assertEqual(payload["summary"]["manual_relations_upserted"], 1)
        self.assertEqual(payload["summary"]["manual_relations_suppressed"], 1)
        import_mock.assert_called_once()
        manual_overrides = import_mock.call_args.kwargs["manual_overrides"]
        self.assertEqual(len(manual_overrides), 2)
        override_map = {
            (item["start_id"], item["end_id"], item["relation_type"]): item["action"]
            for item in manual_overrides
        }
        self.assertEqual(override_map[(syndrome_id, formula_id, "SYNDROME_TO_FORMULA")], "suppress")
        self.assertEqual(override_map[(syndrome_id, symptom_id, "SYNDROME_HAS_SYMPTOM")], "upsert")

    def test_manual_relation_list_defaults_to_active_graph(self):
        data = load_graph_data()
        syndrome_id = next(item["entity_id"] for item in data["entities"].values() if item["entity_type"] == "SYNDROME")
        formula_id = next(item["entity_id"] for item in data["entities"].values() if item["entity_type"] == "FORMULA")

        manual_payload = {
            "records": [
                {
                    "id": "manual-active",
                    "graph_id": "default-graph",
                    "action": "upsert",
                    "relation_type": "SYNDROME_TO_FORMULA",
                    "start_id": syndrome_id,
                    "end_id": formula_id,
                    "evidence_count": 1,
                    "record_ids": [],
                    "example_text": "",
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:00:00+00:00",
                },
                {
                    "id": "manual-global",
                    "graph_id": "",
                    "action": "suppress",
                    "relation_type": "SYNDROME_TO_FORMULA",
                    "start_id": syndrome_id,
                    "end_id": formula_id,
                    "evidence_count": 1,
                    "record_ids": [],
                    "example_text": "",
                    "created_at": "2026-03-24T00:01:00+00:00",
                    "updated_at": "2026-03-24T00:01:00+00:00",
                },
                {
                    "id": "manual-other",
                    "graph_id": "other-graph",
                    "action": "upsert",
                    "relation_type": "SYNDROME_TO_FORMULA",
                    "start_id": syndrome_id,
                    "end_id": formula_id,
                    "evidence_count": 1,
                    "record_ids": [],
                    "example_text": "",
                    "created_at": "2026-03-24T00:02:00+00:00",
                    "updated_at": "2026-03-24T00:02:00+00:00",
                },
            ]
        }
        with open(self.manual_relations_path, "w", encoding="utf-8") as handle:
            json.dump(manual_payload, handle, ensure_ascii=False, indent=2)

        list_response = self.client.get("/api/v1/graph/manual-relations/")
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        self.assertEqual(payload["total"], 2)
        ids = {item["id"] for item in payload["records"]}
        self.assertEqual(ids, {"manual-active", "manual-global"})
