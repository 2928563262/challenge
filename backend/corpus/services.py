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
                "text_length": len(text),
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


def search_corpus(
    keyword: str = "",
    limit: int = 20,
    page: int = 1,
    page_size: int | None = None,
    formula_related: bool | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
) -> dict[str, object]:
    entries = load_corpus_entries()
    normalized_keyword = keyword.strip()
    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size or limit), 100))
    normalized_order = "desc" if str(sort_order).lower() == "desc" else "asc"
    normalized_sort_by = str(sort_by or "id").strip() or "id"

    matches = []
    for entry in entries:
        text = str(entry["text"])
        if normalized_keyword and normalized_keyword not in text:
            continue
        if formula_related is True and not bool(entry["is_formula_related"]):
            continue
        if formula_related is False and bool(entry["is_formula_related"]):
            continue
        matches.append(entry)

    if normalized_sort_by == "text_length":
        matches.sort(key=lambda item: (int(item["text_length"]), int(item["id"])), reverse=normalized_order == "desc")
    elif normalized_sort_by == "formula_name":
        matches.sort(
            key=lambda item: (str(item.get("formula_name") or ""), int(item["id"])),
            reverse=normalized_order == "desc",
        )
    else:
        normalized_sort_by = "id"
        matches.sort(key=lambda item: int(item["id"]), reverse=normalized_order == "desc")

    total = len(matches)
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    if total_pages and safe_page > total_pages:
        safe_page = total_pages
    offset = (safe_page - 1) * safe_page_size
    paged_results = matches[offset : offset + safe_page_size]

    return {
        "keyword": normalized_keyword,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        "has_next": safe_page < total_pages,
        "has_previous": safe_page > 1 and total_pages > 0,
        "formula_related": formula_related,
        "sort_by": normalized_sort_by,
        "sort_order": normalized_order,
        "results": paged_results,
    }
