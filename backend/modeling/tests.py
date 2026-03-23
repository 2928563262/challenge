from django.test import TestCase
from rest_framework.test import APIClient
import torch
from unittest.mock import patch

from .services import _apply_relation_heuristics, _constrain_relation_predictions


class ModelingApiTests(TestCase):
    client_class = APIClient

    def test_model_summary_endpoint_returns_ner_and_relation_sections(self):
        response = self.client.get("/api/v1/model/summary/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ner", payload)
        self.assertIn("relation", payload)
        self.assertIn("accepted_pipeline", payload)
        self.assertIn("dataset_manifest_exists", payload["relation"])
        self.assertIn("checkpoint_exists", payload["relation"])
        self.assertIn("accepted_report", payload["accepted_pipeline"])

    def test_ner_status_endpoint_returns_state(self):
        response = self.client.get("/api/v1/model/ner/status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ready", payload)
        self.assertIn("checkpoint_exists", payload)
        self.assertIn("dataset_manifest_path", payload)

    def test_relation_status_endpoint_returns_state(self):
        response = self.client.get("/api/v1/model/relation/status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ready", payload)
        self.assertIn("checkpoint_exists", payload)
        self.assertIn("dataset_manifest_path", payload)

    def test_ner_predict_requires_text(self):
        response = self.client.post("/api/v1/model/ner/predict/", {}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_relation_predict_requires_text(self):
        response = self.client.post("/api/v1/model/relation/predict/", {"head": {}, "tail": {}}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_relation_predict_requires_head_and_tail_objects(self):
        response = self.client.post(
            "/api/v1/model/relation/predict/",
            {
                "text": "\u592a\u9633\u75c5\uff0c\u5934\u75db\u53d1\u70ed\uff0c\u6842\u679d\u6c64\u4e3b\u4e4b\u3002",
                "head": "not-an-object",
                "tail": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("modeling.views.run_accepted_pipeline_refresh")
    def test_accepted_pipeline_refresh_endpoint_returns_pipeline_report(self, refresh_mock):
        refresh_mock.return_value = {
            "export_report": {"stats": {"record_count": 9}},
            "incremental_report": {"stats": {"accepted_record_count": 9}},
            "merge_report": {"stats": {"ner": {"added_count": 9}}},
            "status": {"accepted_report": {"exists": True}},
        }

        response = self.client.post("/api/v1/model/datasets/accepted/refresh/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["export_report"]["stats"]["record_count"], 9)
        refresh_mock.assert_called_once_with(limit=None)

    def test_accepted_pipeline_refresh_rejects_invalid_limit(self):
        response = self.client.post("/api/v1/model/datasets/accepted/refresh/", {"limit": 0}, format="json")

        self.assertEqual(response.status_code, 400)


class RelationConstraintTests(TestCase):
    def test_constraint_rewrites_incompatible_top_label_for_syndrome_formula_pair(self):
        probabilities = torch.tensor([0.4603, 0.2076, 0.0121, 0.0012, 0.3178])
        id2label = {
            0: "SYNDROME_HAS_SYMPTOM",
            1: "SYNDROME_TO_FORMULA",
            2: "FORMULA_CONTAINS_HERB",
            3: "FORMULA_HAS_ADMINISTRATION",
            4: "NO_RELATION",
        }

        result = _constrain_relation_predictions(probabilities, id2label, "SYNDROME", "FORMULA")

        self.assertEqual(result["raw_label"], "SYNDROME_HAS_SYMPTOM")
        self.assertEqual(result["label"], "NO_RELATION")
        self.assertTrue(result["constraint_applied"])
        self.assertEqual([item["label"] for item in result["top_predictions"]], ["NO_RELATION", "SYNDROME_TO_FORMULA"])

    def test_constraint_returns_only_no_relation_for_unsupported_entity_pair(self):
        probabilities = torch.tensor([0.4, 0.3, 0.2, 0.05, 0.05])
        id2label = {
            0: "SYNDROME_HAS_SYMPTOM",
            1: "SYNDROME_TO_FORMULA",
            2: "FORMULA_CONTAINS_HERB",
            3: "FORMULA_HAS_ADMINISTRATION",
            4: "NO_RELATION",
        }

        result = _constrain_relation_predictions(probabilities, id2label, "HERB", "FORMULA")

        self.assertEqual(result["label"], "NO_RELATION")
        self.assertEqual(result["compatible_labels"], ["NO_RELATION"])
        self.assertEqual([item["label"] for item in result["top_predictions"]], ["NO_RELATION"])

    def test_formula_trigger_promotes_syndrome_to_formula(self):
        constrained = {
            "label": "NO_RELATION",
            "confidence": 0.3178,
            "compatible_labels": ["SYNDROME_TO_FORMULA", "NO_RELATION"],
            "top_predictions": [
                {"label": "NO_RELATION", "score": 0.3178},
                {"label": "SYNDROME_TO_FORMULA", "score": 0.2076},
            ],
        }

        result = _apply_relation_heuristics(
            text="\u592a\u9633\u75c5\uff0c\u5934\u75db\u53d1\u70ed\uff0c\u6c57\u51fa\u6076\u98ce\uff0c\u6842\u679d\u6c64\u4e3b\u4e4b\u3002",
            head={"text": "\u592a\u9633\u75c5", "type": "SYNDROME"},
            tail={"text": "\u6842\u679d\u6c64", "type": "FORMULA"},
            constrained_result=constrained,
        )

        self.assertEqual(result["label"], "SYNDROME_TO_FORMULA")
        self.assertTrue(result["heuristic_override"])
        self.assertEqual(result["heuristic_reason"], "formula_trigger")
