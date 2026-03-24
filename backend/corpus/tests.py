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

    def test_search_endpoint_returns_paginated_results_without_keyword(self):
        response = self.client.get("/api/v1/corpus/search/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("page", payload)
        self.assertIn("page_size", payload)
        self.assertIn("results", payload)

    def test_search_endpoint_returns_matches(self):
        response = self.client.get("/api/v1/corpus/search/", {"keyword": "桂枝汤"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["keyword"], "桂枝汤")
        self.assertGreater(payload["total"], 0)

    def test_search_endpoint_supports_formula_filter_and_sort(self):
        response = self.client.get(
            "/api/v1/corpus/search/",
            {"formula_related": "true", "sort_by": "text_length", "sort_order": "desc", "page": 1, "page_size": 5},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["formula_related"], True)
        self.assertLessEqual(len(payload["results"]), 5)
        if payload["results"]:
            self.assertTrue(all(item["is_formula_related"] for item in payload["results"]))

    def test_search_endpoint_rejects_invalid_sort_parameter(self):
        response = self.client.get("/api/v1/corpus/search/", {"sort_by": "invalid"})

        self.assertEqual(response.status_code, 400)
