from __future__ import annotations

from django.apps import AppConfig


class QAConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "qa"
    verbose_name = "智能问答"
