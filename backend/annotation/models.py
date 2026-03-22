from __future__ import annotations

from uuid import uuid4

from django.db import models


STATUS_PENDING = "pending"
STATUS_REVIEWED = "reviewed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_CHOICES = [
    (STATUS_PENDING, "Pending"),
    (STATUS_REVIEWED, "Reviewed"),
    (STATUS_ACCEPTED, "Accepted"),
    (STATUS_REJECTED, "Rejected"),
]


def generate_record_id() -> str:
    return f"candidate-{uuid4().hex[:12]}"


class AnnotationCandidate(models.Model):
    record_id = models.CharField(max_length=64, unique=True, default=generate_record_id)
    source_text = models.TextField()
    source_page = models.CharField(max_length=64, default="explore")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    node_count = models.PositiveIntegerField(default=0)
    edge_count = models.PositiveIntegerField(default=0)
    session_payload = models.JSONField(default=dict)
    ner_model_dir = models.CharField(max_length=255, blank=True, default="")
    relation_model_dir = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.record_id
