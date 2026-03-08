from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from aimemory.core.utils import ensure_dir
from aimemory.memory_intelligence.policies import MemoryPolicy


@dataclass(slots=True)
class ProviderLiteConfig:
    llm: str = "noop"
    vision: str = "text-only"
    extractor: str = "rule"
    planner: str = "evidence"
    recall_planner: str = "lite"
    reranker: str = "rule"


@dataclass(slots=True)
class AIMemoryConfig:
    root_dir: str | Path = ".aimemory"
    sqlite_path: str | Path | None = None
    object_store_path: str | Path | None = None
    default_user_id: str = "default"
    auto_project: bool = True
    session_ttl_seconds: int = 60 * 60 * 24
    projection_batch_size: int = 100
    index_backend: str = "lancedb"
    graph_backend: str = "kuzu"
    enable_lancedb: bool = False
    enable_kuzu: bool = False
    lancedb_path: str | Path | None = None
    kuzu_path: str | Path | None = None
    intelligence_enabled: bool = True
    providers: ProviderLiteConfig = field(default_factory=ProviderLiteConfig)
    memory_policy: MemoryPolicy = field(default_factory=MemoryPolicy)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: "AIMemoryConfig | dict[str, Any] | None") -> "AIMemoryConfig":
        if value is None:
            return cls().resolved()
        if isinstance(value, cls):
            return value.resolved()
        if isinstance(value, dict):
            payload = dict(value)
            if "providers" in payload and isinstance(payload["providers"], dict):
                payload["providers"] = ProviderLiteConfig(**payload["providers"])
            if "memory_policy" in payload and isinstance(payload["memory_policy"], dict):
                payload["memory_policy"] = MemoryPolicy(**payload["memory_policy"])
            return cls(**payload).resolved()
        raise TypeError("config must be AIMemoryConfig, dict, or None")

    def resolved(self) -> "AIMemoryConfig":
        root_dir = ensure_dir(self.root_dir)
        sqlite_path = Path(self.sqlite_path) if self.sqlite_path else root_dir / "data" / "aimemory.db"
        object_store_path = Path(self.object_store_path) if self.object_store_path else root_dir / "objects"
        lancedb_path = Path(self.lancedb_path) if self.lancedb_path else root_dir / "lancedb"
        kuzu_path = Path(self.kuzu_path) if self.kuzu_path else root_dir / "kuzu"

        ensure_dir(sqlite_path.parent)
        ensure_dir(object_store_path)
        ensure_dir(lancedb_path)
        if self.kuzu_path and Path(self.kuzu_path).suffix:
            ensure_dir(kuzu_path.parent)
        else:
            ensure_dir(kuzu_path)

        return replace(
            self,
            root_dir=root_dir,
            sqlite_path=sqlite_path.resolve(),
            object_store_path=object_store_path.resolve(),
            lancedb_path=lancedb_path.resolve(),
            kuzu_path=kuzu_path.resolve(),
        )
