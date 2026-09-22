"""Typed access to the known-duplicates fixture corpus."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.dedup import RecordForDedup


@dataclass(frozen=True, slots=True)
class ExpectedCluster:
    name: str
    members: frozenset[uuid.UUID]
    primary_id: uuid.UUID
    score: float
    auto_resolvable: bool


@dataclass(frozen=True, slots=True)
class KnownCorpus:
    records: tuple[RecordForDedup, ...]
    by_key: dict[str, RecordForDedup]
    expected_clusters: tuple[ExpectedCluster, ...]
    must_not_cluster: tuple[frozenset[uuid.UUID], ...]


@pytest.fixture(scope="session")
def known_corpus() -> KnownCorpus:
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "dedup" / "known_records.json"
    payload: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))

    records: list[RecordForDedup] = []
    by_key: dict[str, RecordForDedup] = {}
    for raw in payload["records"]:
        record = RecordForDedup(
            id=uuid.UUID(raw["id"]),
            title=raw["title"],
            title_norm=raw["title_norm"],
            authors=tuple(raw["authors"]),
            year=raw["year"],
            journal=raw["journal"],
            volume=raw["volume"],
            issue=raw["issue"],
            pages=raw["pages"],
            doi_norm=raw["doi_norm"],
            pmid=raw["pmid"],
            abstract_present=raw["abstract_present"],
            imported_at=datetime.fromisoformat(raw["imported_at"]),
        )
        records.append(record)
        by_key[raw["key"]] = record

    expected_clusters = tuple(
        ExpectedCluster(
            name=raw["name"],
            members=frozenset(by_key[key].id for key in raw["members"]),
            primary_id=by_key[raw["primary"]].id,
            score=raw["score"],
            auto_resolvable=raw["auto_resolvable"],
        )
        for raw in payload["truth"]["duplicate_groups"]
    )
    must_not_cluster = tuple(
        frozenset(by_key[key].id for key in raw["members"])
        for raw in payload["truth"]["must_not_cluster"]
    )
    return KnownCorpus(tuple(records), by_key, expected_clusters, must_not_cluster)
