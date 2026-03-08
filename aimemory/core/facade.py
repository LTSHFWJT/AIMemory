from __future__ import annotations

import asyncio
from typing import Any

from aimemory.core.capabilities import capability_dict
from aimemory.core.governance import describe_governance_capabilities, describe_memory_type_policies
from aimemory.core.router import RetrievalRouter
from aimemory.core.settings import AIMemoryConfig
from aimemory.memory_intelligence.pipeline import MemoryIntelligencePipeline
from aimemory.providers.factory import LiteProviderFactory
from aimemory.services.archive_service import ArchiveService
from aimemory.services.execution_service import ExecutionService
from aimemory.services.interaction_service import InteractionService
from aimemory.services.knowledge_service import KnowledgeService
from aimemory.services.memory_service import MemoryService
from aimemory.services.projection_service import ProjectionService
from aimemory.services.retrieval_service import RetrievalService
from aimemory.services.skill_service import SkillService
from aimemory.storage.kuzu.graph_store import KuzuGraphStore
from aimemory.storage.lancedb.index_store import LanceIndexStore
from aimemory.storage.object_store.local import LocalObjectStore
from aimemory.storage.sqlite.database import SQLiteDatabase
from aimemory.workers.cleaner import LowValueMemoryCleanerWorker
from aimemory.workers.compactor import SessionCompactionWorker
from aimemory.workers.distiller import SessionMemoryPromoterWorker
from aimemory.workers.governor import GovernanceAutomationWorker
from aimemory.workers.projector import ProjectorWorker


class AIMemory:
    def __init__(self, config: AIMemoryConfig | dict[str, Any] | None = None):
        self.config = AIMemoryConfig.from_value(config)
        self.db = SQLiteDatabase(self.config.sqlite_path)
        self.object_store = LocalObjectStore(self.config.object_store_path)
        use_lancedb_store = self.config.enable_lancedb or self.config.index_backend == "lancedb"
        use_kuzu_store = self.config.enable_kuzu or self.config.graph_backend == "kuzu"
        self.lancedb_store = LanceIndexStore(self.config.lancedb_path) if use_lancedb_store else None
        self.kuzu_store = KuzuGraphStore(self.config.kuzu_path) if use_kuzu_store else None
        self.router = RetrievalRouter()

        self.llm_provider = LiteProviderFactory.create("llm", self.config.providers.llm)
        self.vision_processor = LiteProviderFactory.create("vision", self.config.providers.vision)
        self.fact_extractor = LiteProviderFactory.create("extractor", self.config.providers.extractor)
        self.memory_planner = LiteProviderFactory.create("planner", self.config.providers.planner)
        self.recall_planner = LiteProviderFactory.create("recall_planner", self.config.providers.recall_planner)
        self.reranker = LiteProviderFactory.create("reranker", self.config.providers.reranker)
        self.index_backend = LiteProviderFactory.create(
            "index_backend",
            self.config.index_backend,
            db=self.db,
            config=self.config,
            lancedb_store=self.lancedb_store,
        )
        self.graph_backend = LiteProviderFactory.create(
            "graph_backend",
            self.config.graph_backend,
            db=self.db,
            config=self.config,
            kuzu_store=self.kuzu_store,
        )

        self.projection = ProjectionService(self.db, self.config, index_backend=self.index_backend, graph_backend=self.graph_backend)
        self.interaction = InteractionService(self.db, self.projection, self.config)
        self.execution = ExecutionService(self.db, self.projection, self.config)
        self.memory = MemoryService(self.db, self.projection, self.config, interaction_service=self.interaction)
        self.knowledge = KnowledgeService(self.db, self.projection, self.config, object_store=self.object_store)
        self.skills = SkillService(self.db, self.projection, self.config, object_store=self.object_store)
        self.retrieve = RetrievalService(
            self.db,
            self.config,
            router=self.router,
            reranker=self.reranker,
            index_backend=self.index_backend,
            graph_backend=self.graph_backend,
            recall_planner=self.recall_planner,
        )
        self.memory_pipeline = MemoryIntelligencePipeline(
            vision_processor=self.vision_processor,
            extractor=self.fact_extractor,
            planner=self.memory_planner,
            memory_service=self.memory,
            retrieval_service=self.retrieve,
            policy=self.config.memory_policy,
        )
        self.memory.set_intelligence_pipeline(self.memory_pipeline)
        self.archive = ArchiveService(
            self.db,
            self.projection,
            self.config,
            object_store=self.object_store,
            interaction_service=self.interaction,
            memory_service=self.memory,
        )
        self.projector = ProjectorWorker(self.projection)
        self.distiller = SessionMemoryPromoterWorker(self.memory)
        self.compactor = SessionCompactionWorker(self.interaction)
        self.cleaner = LowValueMemoryCleanerWorker(self.memory, self.archive)
        self.governor = GovernanceAutomationWorker(self.interaction, self.memory, self.cleaner)
        self._closed = False

    def add(self, messages, **kwargs) -> dict[str, Any]:
        kwargs = self._normalize_add_kwargs(kwargs)
        return self.memory.add(messages, **kwargs)

    def get(self, memory_id: str) -> dict[str, Any] | None:
        return self.memory.get(memory_id)

    def get_all(self, **kwargs) -> dict[str, Any]:
        kwargs = self._normalize_list_kwargs(kwargs)
        return self.memory.get_all(**kwargs)

    def search(self, query: str, **kwargs) -> dict[str, Any]:
        kwargs = self._normalize_search_kwargs(kwargs)
        return self.retrieve.search_memory(query, **kwargs)

    def update(self, memory_id: str, **kwargs) -> dict[str, Any]:
        return self.memory.update(memory_id, **kwargs)

    def delete(self, memory_id: str) -> dict[str, Any]:
        return self.memory.delete(memory_id)

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        return self.memory.history(memory_id)

    def memory_store(
        self,
        text: str,
        user_id: str | None = None,
        session_id: str | None = None,
        long_term: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        if "longTerm" in kwargs:
            long_term = bool(kwargs.pop("longTerm"))
        return self.memory.remember(text=text, user_id=user_id, session_id=session_id, long_term=long_term, **kwargs)

    def memory_search(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
        scope: str = "all",
        top_k: int = 5,
        search_threshold: float = 0.0,
        **kwargs,
    ) -> dict[str, Any]:
        top_k = int(kwargs.pop("limit", kwargs.pop("topK", top_k)))
        search_threshold = float(kwargs.pop("threshold", kwargs.pop("searchThreshold", search_threshold)))
        scope = kwargs.pop("scope", scope)
        return self.retrieve.search_memory(
            query,
            user_id=user_id,
            session_id=session_id,
            agent_id=kwargs.pop("agent_id", kwargs.pop("agentId", None)),
            run_id=kwargs.pop("run_id", kwargs.pop("runId", None)),
            actor_id=kwargs.pop("actor_id", kwargs.pop("actorId", None)),
            role=kwargs.pop("role", None),
            scope=scope,
            limit=top_k,
            threshold=search_threshold,
            filters=kwargs.pop("filters", None),
        )

    def memory_list(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        scope: str = "all",
        limit: int = 100,
        offset: int = 0,
        **kwargs,
    ) -> dict[str, Any]:
        page = int(kwargs.pop("page", 1))
        page_size = int(kwargs.pop("page_size", kwargs.pop("pageSize", limit)))
        if page > 1 and offset == 0:
            offset = (page - 1) * page_size
        limit = page_size
        return self.memory.get_all(
            user_id=user_id,
            session_id=session_id,
            scope=scope,
            limit=limit,
            offset=offset,
            filters=kwargs.pop("filters", None),
        )

    def memory_get(self, memory_id: str) -> dict[str, Any] | None:
        return self.memory.get(memory_id)

    def memory_forget(
        self,
        memory_id: str | None = None,
        query: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        scope: str = "all",
        limit: int = 10,
        **kwargs,
    ) -> dict[str, Any]:
        if memory_id:
            return self.memory.delete(memory_id)
        if query:
            return self.memory.delete_by_query(
                query,
                retrieval_service=self.retrieve,
                user_id=user_id,
                session_id=session_id,
                scope=scope,
                limit=limit,
                filters=kwargs.pop("filters", None),
            )
        raise ValueError("Either memory_id or query must be provided.")

    def query(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
        domains: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        threshold: float = 0.0,
    ) -> dict[str, Any]:
        return self.retrieve.retrieve(
            query,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
            domains=domains,
            filters=filters,
            limit=limit,
            threshold=threshold,
        )

    def explain_recall(self, query: str, **kwargs) -> dict[str, Any]:
        return self.retrieve.explain_memory_recall(query, **kwargs)

    def create_session(self, user_id: str, session_id: str | None = None, **kwargs) -> dict[str, Any]:
        return self.interaction.create_session(user_id=user_id, session_id=session_id, **kwargs)

    def append_turn(self, session_id: str, role: str, content: str, **kwargs) -> dict[str, Any]:
        return self.interaction.append_turn(session_id=session_id, role=role, content=content, **kwargs)

    def start_run(self, user_id: str, goal: str, **kwargs) -> dict[str, Any]:
        return self.execution.start_run(user_id=user_id, goal=goal, **kwargs)

    def ingest_document(self, title: str, text: str, **kwargs) -> dict[str, Any]:
        return self.knowledge.ingest_text(title=title, text=text, **kwargs)

    def register_skill(self, name: str, description: str, **kwargs) -> dict[str, Any]:
        return self.skills.register(name=name, description=description, **kwargs)

    def archive_session(self, session_id: str, **kwargs) -> dict[str, Any]:
        return self.archive.archive_session(session_id=session_id, **kwargs)

    def promote_session_memories(self, session_id: str, **kwargs) -> dict[str, Any]:
        return self.memory.promote_session_memories(session_id=session_id, **kwargs)

    def compress_session_context(self, session_id: str, **kwargs) -> dict[str, Any]:
        return self.interaction.compress_session_context(session_id=session_id, **kwargs)

    def session_health(self, session_id: str) -> dict[str, Any]:
        return self.interaction.session_health(session_id)

    def prune_session_snapshots(self, session_id: str, **kwargs) -> dict[str, Any]:
        return self.interaction.prune_snapshots(session_id=session_id, **kwargs)

    def cleanup_low_value_memories(self, **kwargs) -> dict[str, Any]:
        return self.cleaner.run_once(**kwargs)

    def govern_session(self, session_id: str, **kwargs) -> dict[str, Any]:
        return self.governor.run_once(session_id, **kwargs)

    def project(self, limit: int | None = None) -> dict[str, Any]:
        return self.projection.project_pending(limit=limit)

    def describe_capabilities(self) -> dict[str, Any]:
        capabilities = {
            "llm": getattr(self.llm_provider, "describe_capabilities", lambda: capability_dict(category="llm", provider="unknown", features={}))(),
            "vision": getattr(self.vision_processor, "describe_capabilities", lambda: capability_dict(category="vision", provider="unknown", features={}))(),
            "extractor": getattr(self.fact_extractor, "describe_capabilities", lambda: capability_dict(category="extractor", provider="unknown", features={}))(),
            "planner": getattr(self.memory_planner, "describe_capabilities", lambda: capability_dict(category="planner", provider="unknown", features={}))(),
            "recall_planner": getattr(self.recall_planner, "describe_capabilities", lambda: capability_dict(category="recall_planner", provider="unknown", features={}))(),
            "reranker": getattr(self.reranker, "describe_capabilities", lambda: capability_dict(category="reranker", provider="unknown", features={}))(),
            "index_backend": getattr(self.index_backend, "describe_capabilities", lambda: capability_dict(category="index_backend", provider="unknown", features={}))(),
            "graph_backend": getattr(self.graph_backend, "describe_capabilities", lambda: capability_dict(category="graph_backend", provider="unknown", features={}))(),
            "workers": capability_dict(
                category="workers",
                provider="built-in",
                features={
                    "local_workers": True,
                    "governance_automation": True,
                    "background_platform": False,
                },
                items={
                    "projector": getattr(self.projector, "describe_capabilities", lambda: capability_dict(category="worker", provider="unknown", features={}))(),
                    "compactor": getattr(self.compactor, "describe_capabilities", lambda: capability_dict(category="worker", provider="unknown", features={}))(),
                    "distiller": getattr(self.distiller, "describe_capabilities", lambda: capability_dict(category="worker", provider="unknown", features={}))(),
                    "cleaner": getattr(self.cleaner, "describe_capabilities", lambda: capability_dict(category="worker", provider="unknown", features={}))(),
                    "governor": getattr(self.governor, "describe_capabilities", lambda: capability_dict(category="worker", provider="unknown", features={}))(),
                },
            ),
            "governance": describe_governance_capabilities(),
            "memory_type_policy": describe_memory_type_policies(),
        }
        return capabilities

    def close(self) -> None:
        if self._closed:
            return
        self.db.close()
        self._closed = True

    def __enter__(self) -> "AIMemory":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _normalize_add_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(kwargs)
        if "longTerm" in normalized and "long_term" not in normalized:
            normalized["long_term"] = normalized.pop("longTerm")
        if "infer" not in normalized:
            normalized["infer"] = self.config.memory_policy.infer_by_default
        return normalized

    def _normalize_search_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(kwargs)
        if "top_k" in normalized and "limit" not in normalized:
            normalized["limit"] = normalized.pop("top_k")
        if "topK" in normalized and "limit" not in normalized:
            normalized["limit"] = normalized.pop("topK")
        if "search_threshold" in normalized and "threshold" not in normalized:
            normalized["threshold"] = normalized.pop("search_threshold")
        if "searchThreshold" in normalized and "threshold" not in normalized:
            normalized["threshold"] = normalized.pop("searchThreshold")
        return normalized

    def _normalize_list_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(kwargs)
        if "page_size" in normalized and "limit" not in normalized:
            normalized["limit"] = normalized.pop("page_size")
        if "pageSize" in normalized and "limit" not in normalized:
            normalized["limit"] = normalized.pop("pageSize")
        if "page" in normalized and "offset" not in normalized:
            page = int(normalized.pop("page"))
            limit = int(normalized.get("limit", 100))
            normalized["offset"] = max(0, page - 1) * limit
        return normalized


class AsyncAIMemory:
    def __init__(self, config: AIMemoryConfig | dict[str, Any] | None = None):
        self._sync = AIMemory(config)

    async def add(self, messages, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.add, messages, **kwargs)

    async def search(self, query: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.search, query, **kwargs)

    async def memory_store(self, text: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.memory_store, text, **kwargs)

    async def query(self, query: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.query, query, **kwargs)

    async def get(self, memory_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._sync.get, memory_id)

    async def promote_session_memories(self, session_id: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.promote_session_memories, session_id, **kwargs)

    async def compress_session_context(self, session_id: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.compress_session_context, session_id, **kwargs)

    async def session_health(self, session_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.session_health, session_id)

    async def prune_session_snapshots(self, session_id: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.prune_session_snapshots, session_id, **kwargs)

    async def cleanup_low_value_memories(self, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.cleanup_low_value_memories, **kwargs)

    async def govern_session(self, session_id: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.govern_session, session_id, **kwargs)

    async def explain_recall(self, query: str, **kwargs) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.explain_recall, query, **kwargs)

    async def describe_capabilities(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.describe_capabilities)

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)
