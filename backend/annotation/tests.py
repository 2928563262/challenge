from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from annotation.models import AnnotationCandidate


class AnnotationApiTests(TestCase):
    client_class = APIClient

    def test_create_candidate_requires_source_text(self):
        response = self.client.post(
            "/api/v1/annotation/candidates/",
            {"session_payload": {}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_create_candidate_persists_session_payload(self):
        response = self.client.post(
            "/api/v1/annotation/candidates/",
            {
                "source_text": "????????????????????",
                "source_page": "explore",
                "ner_model_dir": "models/baseline/ner",
                "relation_model_dir": "models/baseline/relation",
                "session_payload": {
                    "text": "????????????????????",
                    "node_count": 2,
                    "edge_count": 1,
                    "nodes": [{"text": "???", "type": "SYNDROME"}, {"text": "???", "type": "FORMULA"}],
                    "edges": [{"label": "SYNDROME_TO_FORMULA"}],
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual(payload["edge_count"], 1)
        self.assertEqual(AnnotationCandidate.objects.count(), 1)
        self.assertEqual(AnnotationCandidate.objects.first().source_page, "explore")

    def test_list_candidates_returns_latest_records(self):
        AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 1, "edge_count": 0})
        AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 2, "edge_count": 1})

        response = self.client.get("/api/v1/annotation/candidates/?limit=1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(len(payload["results"]), 1)

    def test_list_candidates_supports_status_filter(self):
        AnnotationCandidate.objects.create(source_text="?", status="pending", session_payload={})
        AnnotationCandidate.objects.create(source_text="?", status="accepted", session_payload={})

        response = self.client.get("/api/v1/annotation/candidates/?status=accepted")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["status"], "accepted")

    def test_get_candidate_detail_returns_payload(self):
        candidate = AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 1, "edge_count": 0, "nodes": []})

        response = self.client.get(f"/api/v1/annotation/candidates/{candidate.record_id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["record_id"], candidate.record_id)
        self.assertIn("session_payload", payload)

    @patch("annotation.views._run_reviewed_graph_refresh_safe")
    @patch("annotation.views._run_accepted_pipeline_refresh_safe")
    def test_patch_candidate_status_updates_record(self, _pipeline_mock, _graph_mock):
        candidate = AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 1, "edge_count": 0})

        response = self.client.patch(
            f"/api/v1/annotation/candidates/{candidate.record_id}/",
            {"status": "accepted"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, "accepted")

    def test_patch_candidate_status_rejects_invalid_value(self):
        candidate = AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 1, "edge_count": 0})

        response = self.client.patch(
            f"/api/v1/annotation/candidates/{candidate.record_id}/",
            {"status": "invalid"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_patch_candidate_supports_updating_payload_and_source_text(self):
        candidate = AnnotationCandidate.objects.create(
            source_text="旧文本",
            session_payload={"text": "旧文本", "node_count": 1, "edge_count": 0, "nodes": [], "edges": []},
        )

        response = self.client.patch(
            f"/api/v1/annotation/candidates/{candidate.record_id}/",
            {
                "source_text": "新文本",
                "session_payload": {
                    "text": "新文本",
                    "node_count": 2,
                    "edge_count": 1,
                    "nodes": [
                        {"key": "n1", "text": "太阳病", "type": "SYNDROME", "start": 0, "end": 3},
                        {"key": "n2", "text": "桂枝汤", "type": "FORMULA", "start": 4, "end": 7},
                    ],
                    "edges": [
                        {
                            "label": "SYNDROME_TO_FORMULA",
                            "head": {"text": "太阳病", "type": "SYNDROME", "start": 0, "end": 3},
                            "tail": {"text": "桂枝汤", "type": "FORMULA", "start": 4, "end": 7},
                            "confidence": 1,
                        }
                    ],
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.source_text, "新文本")
        self.assertEqual(candidate.node_count, 2)
        self.assertEqual(candidate.edge_count, 1)
        self.assertEqual(candidate.session_payload["text"], "新文本")


    @patch("annotation.views._run_reviewed_graph_refresh_safe")
    @patch("annotation.views._run_accepted_pipeline_refresh_safe")
    def test_patch_candidate_status_to_accepted_triggers_auto_refresh(self, refresh_mock, graph_refresh_mock):
        refresh_mock.return_value = {"triggered": True, "ok": True, "export_record_count": 9}
        graph_refresh_mock.return_value = {"triggered": True, "ok": True, "run_name": "graph-reviewed"}
        candidate = AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 1, "edge_count": 0})

        response = self.client.patch(
            f"/api/v1/annotation/candidates/{candidate.record_id}/",
            {"status": "accepted"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("auto_pipeline_refresh", payload)
        self.assertIn("auto_graph_refresh", payload)
        self.assertTrue(payload["auto_pipeline_refresh"]["ok"])
        self.assertTrue(payload["auto_graph_refresh"]["ok"])
        refresh_mock.assert_called_once()
        graph_refresh_mock.assert_called_once()

    @patch("annotation.views._run_reviewed_graph_refresh_safe")
    @patch("annotation.views._run_accepted_pipeline_refresh_safe")
    def test_patch_accepted_candidate_payload_triggers_auto_refresh(self, refresh_mock, graph_refresh_mock):
        refresh_mock.return_value = {"triggered": True, "ok": True, "export_record_count": 10}
        graph_refresh_mock.return_value = {"triggered": True, "ok": True, "run_name": "graph-reviewed"}
        candidate = AnnotationCandidate.objects.create(
            source_text="demo",
            status="accepted",
            session_payload={"text": "demo", "node_count": 1, "edge_count": 0, "nodes": [], "edges": []},
        )

        response = self.client.patch(
            f"/api/v1/annotation/candidates/{candidate.record_id}/",
            {
                "session_payload": {
                    "text": "demo2",
                    "node_count": 1,
                    "edge_count": 0,
                    "nodes": [{"key": "n1", "text": "太阳病", "type": "SYNDROME", "start": 0, "end": 3}],
                    "edges": [],
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("auto_pipeline_refresh", payload)
        self.assertIn("auto_graph_refresh", payload)
        self.assertTrue(payload["auto_pipeline_refresh"]["ok"])
        self.assertTrue(payload["auto_graph_refresh"]["ok"])
        refresh_mock.assert_called_once()
        graph_refresh_mock.assert_called_once()

    @patch("annotation.views._run_reviewed_graph_refresh_safe")
    def test_patch_candidate_status_to_reviewed_triggers_graph_refresh(self, graph_refresh_mock):
        graph_refresh_mock.return_value = {"triggered": True, "ok": True, "run_name": "graph-reviewed"}
        candidate = AnnotationCandidate.objects.create(source_text="?", session_payload={"node_count": 1, "edge_count": 0})

        response = self.client.patch(
            f"/api/v1/annotation/candidates/{candidate.record_id}/",
            {"status": "reviewed"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("auto_graph_refresh", payload)
        self.assertTrue(payload["auto_graph_refresh"]["ok"])
        graph_refresh_mock.assert_called_once()


class AnnotationExportTests(TestCase):
    def test_export_accepted_candidates_writes_jsonl_and_report(self):
        from tempfile import TemporaryDirectory

        from scripts.export_accepted_candidates import export_accepted_candidates

        AnnotationCandidate.objects.create(
            source_text="??????????",
            status="accepted",
            session_payload={
                "nodes": [
                    {"key": "n1", "text": "???", "type": "SYNDROME", "start": 0, "end": 3},
                    {"key": "n2", "text": "???", "type": "FORMULA", "start": 4, "end": 7},
                ],
                "edges": [
                    {
                        "label": "SYNDROME_TO_FORMULA",
                        "head": {"text": "???", "type": "SYNDROME", "start": 0, "end": 3},
                        "tail": {"text": "???", "type": "FORMULA", "start": 4, "end": 7},
                        "confidence": 0.9,
                        "top_predictions": [{"label": "SYNDROME_TO_FORMULA", "score": 0.9}],
                    }
                ],
            },
        )

        with TemporaryDirectory() as tmp_dir:
            report = export_accepted_candidates(Path(tmp_dir))
            self.assertEqual(report["stats"]["record_count"], 1)
            self.assertEqual(report["stats"]["node_count"], 2)
            self.assertEqual(report["stats"]["relation_count"], 1)
            self.assertTrue((Path(tmp_dir) / "accepted_candidates.jsonl").exists())
            self.assertTrue((Path(tmp_dir) / "accepted_candidates_report.json").exists())
