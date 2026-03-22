# Generated manually for challenge annotation candidate workflow.

from django.db import migrations, models

import annotation.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AnnotationCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("record_id", models.CharField(default=annotation.models.generate_record_id, max_length=64, unique=True)),
                ("source_text", models.TextField()),
                ("source_page", models.CharField(default="explore", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("reviewed", "Reviewed"), ("accepted", "Accepted"), ("rejected", "Rejected")],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("node_count", models.PositiveIntegerField(default=0)),
                ("edge_count", models.PositiveIntegerField(default=0)),
                ("session_payload", models.JSONField(default=dict)),
                ("ner_model_dir", models.CharField(blank=True, default="", max_length=255)),
                ("relation_model_dir", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
