from __future__ import annotations

from typing import Any

from aimemory.core.router import RetrievalRouter
from aimemory.core.text import hybrid_score
from aimemory.core.utils import json_loads
from aimemory.memory_intelligence.models import MemoryScopeContext
from aimemory.querying.filters import filter_records


class RetrievalService:
    def __init__(self, db, config, router: RetrievalRouter, reranker=None, index_backend=None, graph_backend=None, recall_planner=None):
        self.db = db
        self.config = config
        self.router = router
        self.reranker = reranker
        self.index_backend = index_backend
        self.graph_backend = graph_backend
        self.recall_planner = recall_planner

    def search_memory(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
        scope: str = "all",
        limit: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = self._build_context(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )
        plan = self.plan_memory_recall(
            query,
            context=context,
            preferred_scope=None if scope == "all" else scope,
            limit=limit,
            auxiliary_limit=self.config.memory_policy.auxiliary_search_limit if scope == "all" else 0,
        )
        results, relations_map = self._execute_memory_recall_plan(query, context=context, plan=plan, threshold=threshold)

        if filters:
            results = filter_records(results, filters)
        results = self._rerank(query, results, domain="memory", context=context)
        relations: list[dict[str, Any]] = []
        for item in results[:limit]:
            relations.extend(relations_map.get(item["id"], []))
        return {"results": results[:limit], "relations": relations, "recall_plan": plan}

    def retrieve(
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
        context = self._build_context(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )
        selected_domains = list(domains or self.router.route(query=query, session_id=session_id))
        if domains is None:
            recall_plan = self.plan_memory_recall(query, context=context, limit=limit)
            merged_domains: list[str] = []
            for handoff_domain in recall_plan.get("handoff_domains", []):
                if handoff_domain not in merged_domains:
                    merged_domains.append(handoff_domain)
            for domain in selected_domains:
                if domain not in merged_domains:
                    merged_domains.append(domain)
            selected_domains = merged_domains
            if "memory" not in selected_domains:
                selected_domains.append("memory")
        results: list[dict[str, Any]] = []
        for domain in selected_domains:
            if domain == "memory":
                results.extend(self._annotate_domain(domain, self.search_memory(query, user_id=user_id, session_id=session_id, agent_id=agent_id, run_id=run_id, actor_id=actor_id, role=role, scope="all", limit=limit, threshold=threshold, filters=filters)["results"]))
            elif domain == "interaction":
                results.extend(self._annotate_domain(domain, self.search_interaction(query, session_id=session_id, actor_id=actor_id, role=role, limit=limit, threshold=threshold, filters=filters)["results"]))
            elif domain == "knowledge":
                results.extend(self._annotate_domain(domain, self.search_knowledge(query, limit=limit, threshold=threshold, filters=filters)["results"]))
            elif domain == "skill":
                results.extend(self._annotate_domain(domain, self.search_skills(query, limit=limit, threshold=threshold, filters=filters)["results"]))
            elif domain == "archive":
                results.extend(self._annotate_domain(domain, self.search_archive(query, user_id=user_id, session_id=session_id, limit=limit, threshold=threshold, filters=filters)["results"]))
            elif domain == "execution":
                results.extend(self._annotate_domain(domain, self.search_execution(query, user_id=user_id, session_id=session_id, limit=limit, threshold=threshold, filters=filters)["results"]))
        results = self._rerank(query, results, domain="global", context=context)
        return {"results": results[:limit], "route": selected_domains}

    def search_interaction(
        self,
        query: str,
        session_id: str | None,
        actor_id: str | None = None,
        role: str | None = None,
        limit: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not session_id:
            return {"results": []}
        context = self._build_context(session_id=session_id, actor_id=actor_id, role=role)
        items: list[dict[str, Any]] = []
        turns = self.db.fetch_all("SELECT * FROM conversation_turns WHERE session_id = ? ORDER BY created_at DESC LIMIT 100", (session_id,))
        for turn in turns:
            item = self._deserialize(turn)
            score = hybrid_score(query, turn["content"])
            if score >= threshold:
                item["score"] = score
                items.append(item)
        snapshots = self.db.fetch_all("SELECT * FROM working_memory_snapshots WHERE session_id = ? ORDER BY created_at DESC LIMIT 20", (session_id,))
        for snapshot in snapshots:
            text = " ".join(part for part in [snapshot.get("summary"), snapshot.get("plan"), snapshot.get("scratchpad")] if part)
            score = hybrid_score(query, text)
            if score >= threshold:
                item = self._deserialize(snapshot)
                item["score"] = score
                items.append(item)
        if filters:
            items = filter_records(items, filters)
        items = self._rerank(query, items, domain="interaction", context=context)
        return {"results": items[:limit]}

    def search_knowledge(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = self.index_backend.search_knowledge_chunks(query, limit=max(limit * 3, 30))
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for row in rows:
            record_id = row.get("record_id")
            if not record_id or record_id in seen_ids:
                continue
            score = float(row.get("score", 0.0))
            if score < threshold:
                continue
            item = self._deserialize(row)
            item["score"] = score
            seen_ids.add(record_id)
            results.append(item)
        if filters:
            results = filter_records(results, filters)
        results = self._rerank(query, results, domain="knowledge", context=self._build_context())
        return {"results": results[:limit]}

    def search_skills(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = self.index_backend.search_skill_records(query, limit=max(limit * 3, 30))
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for row in rows:
            record_id = row.get("record_id")
            if not record_id or record_id in seen_ids:
                continue
            score = float(row.get("score", 0.0))
            if score < threshold:
                continue
            skill = self.db.fetch_one("SELECT * FROM skills WHERE id = ?", (row["skill_id"],))
            item = self._deserialize(row)
            item["skill"] = self._deserialize(skill)
            item["score"] = score
            seen_ids.add(record_id)
            results.append(item)
        if filters:
            results = filter_records(results, filters)
        results = self._rerank(query, results, domain="skill", context=self._build_context())
        return {"results": results[:limit]}

    def search_archive(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = self.index_backend.search_archive_summaries(query, user_id=user_id, session_id=session_id, limit=max(limit * 3, 30))
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for row in rows:
            record_id = row.get("record_id")
            if not record_id or record_id in seen_ids:
                continue
            score = float(row.get("score", 0.0))
            if score < threshold:
                continue
            item = self._deserialize(row)
            item["score"] = score
            seen_ids.add(record_id)
            results.append(item)
        if filters:
            results = filter_records(results, filters)
        results = self._rerank(query, results, domain="archive", context=self._build_context(user_id=user_id, session_id=session_id))
        return {"results": results[:limit]}

    def search_execution(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sql_filters = ["1 = 1"]
        params: list[Any] = []
        if user_id:
            sql_filters.append("user_id = ?")
            params.append(user_id)
        if session_id:
            sql_filters.append("session_id = ?")
            params.append(session_id)
        runs = self.db.fetch_all(f"SELECT * FROM runs WHERE {' AND '.join(sql_filters)} ORDER BY updated_at DESC LIMIT 50", tuple(params))
        items: list[dict[str, Any]] = []
        for run in runs:
            score = hybrid_score(query, " ".join(part for part in [run.get("goal"), run.get("status")] if part))
            if score >= threshold:
                item = self._deserialize(run)
                item["score"] = score
                items.append(item)
            tasks = self.db.fetch_all("SELECT * FROM tasks WHERE run_id = ? ORDER BY updated_at DESC", (run["id"],))
            for task in tasks:
                score = hybrid_score(query, " ".join(part for part in [task.get("title"), task.get("status")] if part))
                if score >= threshold:
                    item = self._deserialize(task)
                    item["score"] = score
                    items.append(item)
            observations = self.db.fetch_all("SELECT * FROM observations WHERE run_id = ? ORDER BY created_at DESC", (run["id"],))
            for observation in observations:
                score = hybrid_score(query, observation.get("content"))
                if score >= threshold:
                    item = self._deserialize(observation)
                    item["score"] = score
                    items.append(item)
        if filters:
            items = filter_records(items, filters)
        items = self._rerank(query, items, domain="execution", context=self._build_context(user_id=user_id, session_id=session_id))
        return {"results": items[:limit]}

    def _relations_for_ref(self, ref_id: str) -> list[dict[str, Any]]:
        if getattr(self, "graph_backend", None) is None:
            return []
        capabilities = getattr(self.graph_backend, "describe_capabilities", lambda: {"features": {}})()
        if not bool(dict(capabilities.get("features") or {}).get("relations", False)):
            return []
        return self.graph_backend.relations_for_ref(ref_id, limit=12)

    def _graph_context(self, query: str, relations: list[dict[str, Any]]) -> dict[str, Any]:
        matched_count = 0
        top_relation_score = 0.0
        relation_types: set[str] = set()
        for relation in relations:
            relation_types.add(str(relation.get("edge_type") or ""))
            relation_text = " ".join(
                part
                for part in [
                    str(relation.get("edge_type") or ""),
                    str(relation.get("source_ref") or ""),
                    str(relation.get("target_ref") or ""),
                    str(relation.get("target_label") or ""),
                ]
                if part
            )
            metadata = dict(relation.get("metadata") or {})
            relation_score = hybrid_score(query, relation_text, metadata.get("keywords"))
            if relation_score >= 0.12:
                matched_count += 1
            top_relation_score = max(top_relation_score, relation_score)
        return {
            "relation_count": len(relations),
            "matched_relation_count": matched_count,
            "top_relation_score": round(top_relation_score, 6),
            "relation_types": sorted(item for item in relation_types if item),
        }

    def _build_context(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
    ) -> MemoryScopeContext:
        return MemoryScopeContext(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )

    def _match_context(self, item: dict[str, Any], context: MemoryScopeContext) -> bool:
        metadata = dict(item.get("metadata") or {})
        if context.user_id and item.get("user_id") != context.user_id:
            return False
        if context.session_id and item.get("session_id") not in {None, context.session_id} and item.get("scope") == "session":
            return False
        if context.agent_id and metadata.get("agent_id") not in {None, context.agent_id} and item.get("agent_id") not in {None, context.agent_id}:
            return False
        if context.run_id and metadata.get("run_id") not in {None, context.run_id} and item.get("run_id") not in {None, context.run_id}:
            return False
        if context.actor_id and metadata.get("actor_id") not in {None, context.actor_id}:
            return False
        if context.role and metadata.get("role") not in {None, context.role}:
            return False
        return True

    def _annotate_domain(self, domain: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            row["domain"] = domain
        return rows

    def _promote_memory(self, item: dict[str, Any] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        metadata = dict(item.get("metadata") or {})
        for field in ("actor_id", "role", "agent_id", "run_id"):
            if item.get(field) is None and field in metadata:
                item[field] = metadata[field]
        return item

    def _rerank(self, query: str, rows: list[dict[str, Any]], *, domain: str, context: MemoryScopeContext) -> list[dict[str, Any]]:
        if self.reranker is None:
            rows.sort(key=lambda item: item.get("score", 0.0), reverse=True)
            return rows
        return self.reranker.rerank(query, rows, domain=domain, context=context, policy=self.config.memory_policy)

    def plan_memory_recall(
        self,
        query: str,
        *,
        context: MemoryScopeContext,
        preferred_scope: str | None = None,
        limit: int | None = None,
        auxiliary_limit: int | None = None,
    ) -> dict[str, Any]:
        if self.recall_planner is not None:
            return self.recall_planner.plan(
                query,
                context=context,
                policy=self.config.memory_policy,
                preferred_scope=preferred_scope,
                limit=limit,
                auxiliary_limit=auxiliary_limit,
                graph_enabled=bool(dict(getattr(self.graph_backend, "describe_capabilities", lambda: {"features": {}})().get("features") or {}).get("relations", False)),
            )
        primary_scope = preferred_scope or ("session" if context.session_id else "long-term")
        secondary_scope = "long-term" if primary_scope == "session" else "session"
        stages = [{"name": "primary", "scope": primary_scope, "limit": int(limit or self.config.memory_policy.search_limit), "targetable": True, "score_bias": 0.0}]
        fallback_aux_limit = int(auxiliary_limit if auxiliary_limit is not None else self.config.memory_policy.auxiliary_search_limit)
        if fallback_aux_limit > 0:
            stages.append({"name": "auxiliary", "scope": secondary_scope, "limit": fallback_aux_limit, "targetable": False, "score_bias": 0.0})
        return {
            "strategy_scope": "run" if context.run_id else "agent" if context.agent_id else "user",
            "strategy_name": f"fallback-{primary_scope}-first",
            "graph_enrichment": True,
            "stages": stages,
        }

    def explain_memory_recall(
        self,
        query: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
        preferred_scope: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        context = self._build_context(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )
        return self.plan_memory_recall(query, context=context, preferred_scope=preferred_scope, limit=limit)

    def _execute_memory_recall_plan(
        self,
        query: str,
        *,
        context: MemoryScopeContext,
        plan: dict[str, Any],
        threshold: float,
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        results: list[dict[str, Any]] = []
        relations_map: dict[str, list[dict[str, Any]]] = {}
        seen_ids: set[str] = set()
        for stage in plan.get("stages", []):
            if int(stage.get("limit", 0)) <= 0:
                continue
            stage_memory_types = set(stage.get("memory_types") or [])
            stage_strategy_scopes = set(stage.get("strategy_scopes") or [])
            rows = self.index_backend.search_memory_candidates(
                query,
                user_id=context.user_id,
                session_id=context.session_id,
                scope=stage.get("scope", "all"),
                limit=max(int(stage.get("limit", 10)) * 4, 20),
            )
            for row in rows:
                record_id = row.get("record_id")
                if not record_id:
                    continue
                memory = self.db.fetch_one("SELECT * FROM memories WHERE id = ?", (record_id,))
                if not memory or memory["status"] != "active":
                    continue
                item = self._promote_memory(self._deserialize(memory))
                if not self._match_context(item, context):
                    continue
                metadata = dict(item.get("metadata") or {})
                if stage_memory_types and str(item.get("memory_type")) not in stage_memory_types:
                    continue
                if stage_strategy_scopes and str(metadata.get("strategy_scope") or "user") not in stage_strategy_scopes:
                    continue
                base_score = float(row.get("score", 0.0))
                score = base_score + float(stage.get("score_bias", 0.0))
                if score < threshold:
                    continue
                existing = next((candidate for candidate in results if candidate["id"] == record_id), None)
                if existing is not None and float(existing.get("score", 0.0)) >= score:
                    continue
                relations = self._relations_for_ref(item["id"])
                item["score"] = round(score, 6)
                item["recall_stage"] = stage.get("name", "primary")
                item["recall_scope"] = stage.get("scope")
                item["targetable"] = bool(stage.get("targetable", True))
                item["graph_context"] = self._graph_context(query, relations)
                if existing is not None:
                    results = [candidate for candidate in results if candidate["id"] != record_id]
                elif record_id in seen_ids:
                    continue
                seen_ids.add(record_id)
                results.append(item)
                relations_map[item["id"]] = relations
        return results, relations_map

    def _deserialize(self, row: dict[str, Any] | None, json_fields: tuple[str, ...] = ("metadata",)) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for field in json_fields:
            if field in item:
                item[field] = json_loads(item.get(field), {})
        return item
