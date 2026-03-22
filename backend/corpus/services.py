from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

FORMULA_PATTERN = re.compile(r"([\u4e00-\u9fa5]{2,}(?:汤|散|丸|饮|方))")


@lru_cache(maxsize=1)
def load_corpus_entries() -> list[dict[str, object]]:
    source_path = Path(settings.DATA_DIR) / "clean_text" / "shanghanlun_cleaned.txt"
    lines = source_path.read_text(encoding="utf-8").splitlines()

    entries: list[dict[str, object]] = []
    for index, raw_line in enumerate(lines, start=1):
        text = raw_line.strip()
        if not text:
            continue

        formula_match = FORMULA_PATTERN.search(text)
        entries.append(
            {
                "id": index,
                "text": text,
                "formula_name": formula_match.group(1) if formula_match else None,
                "is_formula_related": bool(formula_match),
            }
        )

    return entries


def build_overview_payload() -> dict[str, object]:
    entries = load_corpus_entries()
    formula_entries = [entry for entry in entries if entry["is_formula_related"]]

    return {
        "project": {
            "name": "《伤寒论》知识图谱 MVP",
            "focus": "文本整理、条文检索与知识图谱演示骨架",
        },
        "stats": {
            "entry_count": len(entries),
            "formula_related_count": len(formula_entries),
            "character_count": sum(len(str(entry["text"])) for entry in entries),
        },
        "samples": entries[:5],
        "formula_samples": formula_entries[:8],
    }


def search_corpus(keyword: str, limit: int = 20) -> dict[str, object]:
    entries = load_corpus_entries()
    matches = [entry for entry in entries if keyword in str(entry["text"])]

    return {
        "keyword": keyword,
        "total": len(matches),
        "results": matches[:limit],
    }
