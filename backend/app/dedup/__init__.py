"""Duplicate detection: blocking, pairwise scoring and clustering (guide 9.1)."""

from app.dedup.blocking import blocks
from app.dedup.clustering import cluster
from app.dedup.normalisation import normalise_title
from app.dedup.scoring import score_pair
from app.dedup.types import Cluster, RecordForDedup

__all__ = [
    "Cluster",
    "RecordForDedup",
    "blocks",
    "cluster",
    "normalise_title",
    "score_pair",
]
