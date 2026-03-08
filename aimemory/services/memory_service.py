from __future__ import annotations

from typing import Any

from aimemory.core.governance import (
    evaluate_memory_value,
    governance_scope_rules,
    memory_type_policy_profile,
    resolve_strategy_scope,
)
from aimemory.memory_intelligence.models import MessagePart, MemoryScopeContext, NormalizedMessage
from aimemory.querying.filters import filter_records
from aimemory.core.text import build_summary, extract_keywords, split_sentences
from aimemory.core.utils import json_dumps, make_id, merge_metadata, utcnow_iso
from aimemory.domains.memory.models import MemoryScope, MemoryType
from aimemory.services.base import ServiceBase


class MemoryService(ServiceBase):
    def __init__(self, db, projection, config, interaction_service, intelligence_pipeline=None):
        super().__init__(db=db, projection=projection, config=config)
        self.interaction_service = interaction_service
        self.intelligence_pipeline = intelligence_pipeline

    def set_intelligence_pipeline(self, pipeline) -> None:
        self.intelligence_pipeline = pipeline

    def add(
        self,
        messages: str | dict[str, Any] | list[dict[str, Any]],
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
        metadata: dict[str, Any] | None = None,
        memory_type: str | None = None,
        importance: float = 0.5,
        long_term: bool = True,
        source: str = "conversation",
        record_turns: bool = True,
        infer: bool = True,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        effective_user_id = user_id or self.config.default_user_id
        scope_context = self.build_scope_context(
            user_id=effective_user_id,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )
        normalized_messages = self._normalize_messages(messages)
        if session_id and record_turns:
            for message in normalized_messages:
                self.interaction_service.append_turn(
                    session_id=session_id,
                    role=message.role,
                    content=message.content,
                    run_id=run_id,
                    user_id=effective_user_id,
                    metadata=message.metadata,
                    name=message.actor_id,
                )

        if self.intelligence_pipeline and self.config.intelligence_enabled:
            return self.intelligence_pipeline.add(
                normalized_messages,
                context=scope_context,
                metadata=metadata,
                long_term=long_term,
                memory_type=memory_type if memory_type else None,
                source=source,
                infer=infer if infer is not None else self.config.memory_policy.infer_by_default,
            )

        candidates = self._extract_candidates(normalized_messages)
        if not candidates and isinstance(messages, str):
            candidates = [messages]
        if not candidates:
            raise ValueError("No memory candidates were extracted from messages.")

        results = [
            self.remember(
                text=candidate,
                user_id=effective_user_id,
                agent_id=agent_id,
                session_id=session_id,
                run_id=run_id,
                actor_id=actor_id,
                role=role,
                metadata=metadata,
                memory_type=memory_type or str(MemoryType.SEMANTIC),
                importance=importance,
                long_term=long_term,
                source=source,
            )
            for candidate in candidates
        ]
        return {"results": results, "scope": self._scope_from_bool(long_term)}

    def remember(
        self,
        text: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
        metadata: dict[str, Any] | None = None,
        memory_type: str = MemoryType.SEMANTIC,
        importance: float = 0.5,
        long_term: bool = True,
        source: str = "explicit",
    ) -> dict[str, Any]:
        effective_user_id = user_id or self.config.default_user_id
        scope = self._scope_from_bool(long_term)
        resolved_memory_type = self._resolve_memory_type(
            memory_type,
            text=text,
            agent_id=agent_id,
            run_id=run_id,
            role=role,
        )
        metadata = dict(metadata or {})
        existing = self.db.fetch_one(
            """
            SELECT * FROM memories
            WHERE user_id = ? AND COALESCE(session_id, '') = COALESCE(?, '') AND scope = ? AND text = ? AND status != 'deleted'
            LIMIT 1
            """,
            (effective_user_id, session_id, scope, text),
        )
        now = utcnow_iso()
        summary = build_summary(split_sentences(text), max_sentences=2, max_chars=120)
        scope_context = self.build_scope_context(
            user_id=effective_user_id,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )
        base_metadata = merge_metadata(scope_context.as_metadata(), metadata)
        base_metadata.setdefault(
            "strategy_scope",
            resolve_strategy_scope(
                str(resolved_memory_type),
                agent_id=agent_id,
                run_id=run_id,
                role=role,
                metadata=base_metadata,
                text=text,
            ),
        )
        if existing:
            merged_metadata = merge_metadata(self._deserialize_row(existing).get("metadata"), base_metadata)
            updated_importance = max(float(existing["importance"]), importance)
            self.db.execute(
                """
                UPDATE memories
                SET importance = ?, metadata = ?, updated_at = ?, summary = ?, source = ?, memory_type = ?
                WHERE id = ?
                """,
                (updated_importance, json_dumps(merged_metadata), now, summary, source, str(resolved_memory_type), existing["id"]),
            )
            memory_id = existing["id"]
            event_type = "refreshed"
        else:
            memory_id = make_id("mem")
            self.db.execute(
                """
                INSERT INTO memories(id, user_id, agent_id, session_id, run_id, scope, memory_type, text, summary, importance, status, source, metadata, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    effective_user_id,
                    agent_id,
                    session_id,
                    run_id,
                    scope,
                    str(resolved_memory_type),
                    text,
                    summary,
                    importance,
                    source,
                    json_dumps(base_metadata),
                    now,
                    now,
                    None,
                ),
            )
            event_type = "created"

        current = self.get(memory_id)
        event_payload = {
            "text": text,
            "scope": scope,
            "importance": current["importance"],
            "metadata": current.get("metadata", {}),
        }
        self.db.execute(
            "INSERT INTO memory_events(id, memory_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (make_id("mevt"), memory_id, event_type, json_dumps(event_payload), now),
        )
        self.projection.enqueue(
            topic="memory.index",
            entity_type="memory",
            entity_id=memory_id,
            action="upsert",
            payload={
                "record_id": memory_id,
                "user_id": effective_user_id,
                "session_id": session_id,
                "scope": scope,
                "text": text,
                "keywords": extract_keywords(text),
                "score_boost": round(float(current["importance"]) * 0.2, 6),
                "metadata": current.get("metadata", {}),
                "updated_at": current["updated_at"],
            },
        )
        if self.config.auto_project:
            self.projection.project_pending()
        return current

    def get(self, memory_id: str) -> dict[str, Any] | None:
        row = self.db.fetch_one("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return self._promote_memory_row(self._deserialize_row(row))

    def get_all(
        self,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
        strategy_scope: str | None = None,
        scope: str = MemoryScope.LONG_TERM,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sql_filters = ["1 = 1"]
        params: list[Any] = []
        if user_id:
            sql_filters.append("user_id = ?")
            params.append(user_id)
        if agent_id:
            sql_filters.append("agent_id = ?")
            params.append(agent_id)
        if session_id:
            sql_filters.append("session_id = ?")
            params.append(session_id)
        if run_id:
            sql_filters.append("run_id = ?")
            params.append(run_id)
        if scope != "all":
            sql_filters.append("scope = ?")
            params.append(scope)
        if not include_deleted:
            sql_filters.append("status != 'deleted'")
        params.extend([limit, offset])
        rows = self.db.fetch_all(
            f"""
            SELECT * FROM memories
            WHERE {' AND '.join(sql_filters)}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        items = [self._promote_memory_row(item) for item in self._deserialize_rows(rows)]
        if actor_id:
            items = [item for item in items if item.get("actor_id") == actor_id]
        if role:
            items = [item for item in items if item.get("role") == role]
        if strategy_scope:
            items = [item for item in items if dict(item.get("metadata") or {}).get("strategy_scope") == strategy_scope]
        if filters:
            items = filter_records(items, filters)
        return {"results": items}

    def promote_session_memories(
        self,
        session_id: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        min_importance: float = 0.55,
        include_memory_types: list[str] | None = None,
        force: bool = False,
        archive_after_promotion: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.interaction_service.get_session(session_id)
        effective_user_id = user_id or (session.get("user_id") if session else None) or self.config.default_user_id
        allowed_types = set(include_memory_types or [])
        session_memories = self.get_all(
            user_id=effective_user_id,
            session_id=session_id,
            run_id=run_id,
            scope=MemoryScope.SESSION,
            limit=limit,
        )["results"]

        selected: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for item in session_memories:
            if item.get("status") != "active":
                skipped.append({"id": item["id"], "reason": "inactive"})
                continue
            requested_agent_id = agent_id or (session.get("agent_id") if session else None)
            if requested_agent_id and item.get("agent_id") not in {None, requested_agent_id}:
                skipped.append({"id": item["id"], "reason": "agent-filtered"})
                continue
            current_metadata = dict(item.get("metadata") or {})
            strategy_scope = str(
                current_metadata.get("strategy_scope")
                or resolve_strategy_scope(
                    item.get("memory_type"),
                    agent_id=item.get("agent_id"),
                    run_id=item.get("run_id"),
                    role=item.get("role"),
                    metadata=current_metadata,
                    text=item.get("text"),
                )
            )
            scope_rules = governance_scope_rules(strategy_scope)
            type_rules = memory_type_policy_profile(item.get("memory_type"))
            allowed_scope_types = set(scope_rules.get("promotable_memory_types", []))
            if allowed_types and item.get("memory_type") not in allowed_types:
                skipped.append({"id": item["id"], "reason": "memory-type-filtered"})
                continue
            if not allowed_types and allowed_scope_types and item.get("memory_type") not in allowed_scope_types:
                skipped.append({"id": item["id"], "reason": "scope-policy-not-promotable"})
                continue
            required_importance = max(
                float(min_importance),
                float(scope_rules.get("promotion_min_importance", 0.0)),
                float(type_rules.get("promotion_min_importance", 0.0)),
            )
            if float(item.get("importance", 0.0)) < required_importance:
                skipped.append({"id": item["id"], "reason": "importance-too-low", "required_importance": round(required_importance, 6)})
                continue
            if not force and not bool(scope_rules.get("promotion_enabled", True)):
                skipped.append({"id": item["id"], "reason": f"{strategy_scope}-scope-not-promoted"})
                continue
            promotion_state = dict(current_metadata.get("promotion") or {})
            if not force and promotion_state.get("status") == "promoted":
                skipped.append({"id": item["id"], "reason": "already-promoted"})
                continue
            selected.append(item)

        if not selected:
            return {"source_count": 0, "promoted_count": 0, "results": [], "source_ids": [], "skipped": skipped}

        context = self.build_scope_context(
            user_id=effective_user_id,
            agent_id=agent_id or (session.get("agent_id") if session else None),
            session_id=session_id,
            run_id=run_id,
        )
        source_ids = [item["id"] for item in selected]
        promotion_metadata = dict(metadata or {})
        promotion_metadata.setdefault("promotion_source", "session-distillation")
        promotion_metadata.setdefault("distilled_from_session", session_id)
        promotion_metadata.setdefault("source_memory_ids", source_ids)

        normalized_messages: list[NormalizedMessage] = []
        for item in selected:
            item_metadata = dict(item.get("metadata") or {})
            item_metadata.update(
                {
                    "source_memory_id": item["id"],
                    "source_scope": item.get("scope"),
                    "distilled_from_session": session_id,
                }
            )
            normalized_messages.append(
                NormalizedMessage(
                    role=str(item_metadata.get("source_role") or item_metadata.get("role") or "user"),
                    content=item["text"],
                    actor_id=item.get("actor_id"),
                    metadata=item_metadata,
                    parts=[MessagePart(kind="text", text=item["text"])],
                )
            )

        if self.intelligence_pipeline is not None and self.config.intelligence_enabled:
            result = self.intelligence_pipeline.add(
                normalized_messages,
                context=context,
                metadata=promotion_metadata,
                long_term=True,
                source="session-distillation",
                infer=True,
            )
        else:
            promoted_results: list[dict[str, Any]] = []
            for item in selected:
                promoted = self.remember(
                    text=item["text"],
                    user_id=effective_user_id,
                    agent_id=agent_id or (session.get("agent_id") if session else None),
                    session_id=session_id,
                    run_id=run_id,
                    metadata=merge_metadata(item.get("metadata"), promotion_metadata),
                    memory_type=item.get("memory_type") or str(MemoryType.SEMANTIC),
                    importance=max(float(item.get("importance", 0.5)), min_importance),
                    long_term=True,
                    source="session-distillation",
                )
                promoted_results.append({"id": promoted["id"], "memory": promoted["text"], "event": "ADD"})
            result = {"results": promoted_results, "facts": [item["text"] for item in selected]}

        promoted_at = utcnow_iso()
        for item in selected:
            current_metadata = dict(item.get("metadata") or {})
            current_metadata["promotion"] = {
                "status": "promoted",
                "target_scope": str(MemoryScope.LONG_TERM),
                "promoted_at": promoted_at,
            }
            self.update(
                item["id"],
                metadata=current_metadata,
                status="archived" if archive_after_promotion else item.get("status"),
                timestamp=promoted_at,
            )

        return {
            "source_count": len(selected),
            "promoted_count": len(result.get("results", [])),
            "results": result.get("results", []),
            "facts": result.get("facts", []),
            "source_ids": source_ids,
            "skipped": skipped,
        }

    def plan_low_value_cleanup(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        scope: str = MemoryScope.LONG_TERM,
        limit: int = 100,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        effective_threshold = float(
            threshold
            if threshold is not None
            else getattr(self.config.memory_policy, "cleanup_importance_threshold", 0.34)
        )
        items = self.get_all(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            scope=scope,
            limit=limit,
        )["results"]
        candidates: list[dict[str, Any]] = []
        for item in items:
            if item.get("status") != "active":
                continue
            evaluation = evaluate_memory_value(item)
            if float(evaluation["recency_score"]) > float(getattr(self.config.memory_policy, "cleanup_recent_score_ceiling", 0.08)):
                continue
            item_threshold = float(threshold if threshold is not None else evaluation["cleanup_threshold"])
            if float(evaluation["value_score"]) <= item_threshold:
                candidates.append(
                    {
                        "id": item["id"],
                        "text": item["text"],
                        "memory_type": item.get("memory_type"),
                        "strategy_scope": evaluation["strategy_scope"],
                        "value_score": evaluation["value_score"],
                        "cleanup_threshold": round(item_threshold, 6),
                        "suggested_action": evaluation["cleanup_action"],
                        "evaluation": evaluation,
                    }
                )
        candidates.sort(key=lambda item: (float(item["value_score"]), len(item["text"])), reverse=False)
        return {"threshold": effective_threshold, "results": candidates}

    def update(
        self,
        memory_id: str,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
        status: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        current = self.get(memory_id)
        if current is None:
            raise ValueError(f"Memory `{memory_id}` does not exist.")
        updated_text = text or current["text"]
        updated_metadata = merge_metadata(current.get("metadata"), metadata)
        updated_importance = importance if importance is not None else current["importance"]
        updated_status = status or current["status"]
        updated_at = timestamp or utcnow_iso()
        self.db.execute(
            """
            UPDATE memories
            SET text = ?, summary = ?, importance = ?, status = ?, metadata = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                updated_text,
                build_summary(split_sentences(updated_text), max_sentences=2, max_chars=120),
                updated_importance,
                updated_status,
                json_dumps(updated_metadata),
                updated_at,
                memory_id,
            ),
        )
        payload = {"text": updated_text, "metadata": updated_metadata, "importance": updated_importance, "status": updated_status}
        self.db.execute(
            "INSERT INTO memory_events(id, memory_id, event_type, payload, created_at) VALUES (?, ?, 'updated', ?, ?)",
            (make_id("mevt"), memory_id, json_dumps(payload), updated_at),
        )
        result = self.get(memory_id)
        self.projection.enqueue(
            topic="memory.index",
            entity_type="memory",
            entity_id=memory_id,
            action="upsert",
            payload={
                "record_id": memory_id,
                "user_id": result.get("user_id"),
                "session_id": result.get("session_id"),
                "scope": result.get("scope"),
                "text": result.get("text"),
                "keywords": extract_keywords(result.get("text")),
                "score_boost": round(float(result["importance"]) * 0.2, 6),
                "metadata": result.get("metadata", {}),
                "updated_at": result["updated_at"],
            },
        )
        if self.config.auto_project:
            self.projection.project_pending()
        return result

    def delete(self, memory_id: str) -> dict[str, Any]:
        current = self.get(memory_id)
        if current is None:
            raise ValueError(f"Memory `{memory_id}` does not exist.")
        now = utcnow_iso()
        self.db.execute("UPDATE memories SET status = 'deleted', updated_at = ? WHERE id = ?", (now, memory_id))
        self.db.execute(
            "INSERT INTO memory_events(id, memory_id, event_type, payload, created_at) VALUES (?, ?, 'deleted', ?, ?)",
            (make_id("mevt"), memory_id, json_dumps({"id": memory_id}), now),
        )
        self.projection.enqueue("memory.index", "memory", memory_id, "delete", {"record_id": memory_id})
        if self.config.auto_project:
            self.projection.project_pending()
        return {"message": "Memory deleted successfully!", "id": memory_id}

    def delete_by_query(
        self,
        query: str,
        retrieval_service,
        user_id: str | None = None,
        session_id: str | None = None,
        scope: str = "all",
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        results = retrieval_service.search_memory(query, user_id=user_id, session_id=session_id, scope=scope, limit=limit, filters=filters)
        deleted_ids: list[str] = []
        for item in results["results"]:
            self.delete(item["id"])
            deleted_ids.append(item["id"])
        return {"message": "Memories deleted successfully!", "ids": deleted_ids}

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM memory_events WHERE memory_id = ? ORDER BY created_at ASC",
            (memory_id,),
        )
        return self._deserialize_rows(rows, ("payload",))

    def _scope_from_bool(self, long_term: bool) -> str:
        return str(MemoryScope.LONG_TERM if long_term else MemoryScope.SESSION)

    def build_scope_context(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        actor_id: str | None = None,
        role: str | None = None,
    ) -> MemoryScopeContext:
        return MemoryScopeContext(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            actor_id=actor_id,
            role=role,
        )

    def _normalize_messages(self, messages: str | dict[str, Any] | list[dict[str, Any]] | list[NormalizedMessage]) -> list[NormalizedMessage]:
        if messages and isinstance(messages, list) and isinstance(messages[0], NormalizedMessage):
            return messages
        if self.intelligence_pipeline is not None:
            return self.intelligence_pipeline.vision_processor.normalize(messages)
        if isinstance(messages, str):
            return [NormalizedMessage(role="user", content=messages, parts=[MessagePart(kind="text", text=messages)])]
        if isinstance(messages, dict):
            return [
                NormalizedMessage(
                    role=messages.get("role", "user"),
                    content=self._message_content(messages.get("content")),
                    actor_id=messages.get("name"),
                    metadata=messages.get("metadata") or {},
                )
            ]
        normalized: list[NormalizedMessage] = []
        for item in messages:
            normalized.append(
                NormalizedMessage(
                    role=item.get("role", "user"),
                    content=self._message_content(item.get("content")),
                    actor_id=item.get("name"),
                    metadata=item.get("metadata") or {},
                )
            )
        return normalized

    def _message_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.append(str(part.get("text") or part.get("content") or ""))
            return " ".join(part for part in parts if part)
        if isinstance(content, dict):
            return str(content.get("text") or content.get("content") or "")
        return str(content)

    def _resolve_memory_type(
        self,
        memory_type: str | None,
        *,
        text: str,
        agent_id: str | None,
        run_id: str | None,
        role: str | None,
    ) -> str:
        normalized = str(memory_type or MemoryType.SEMANTIC)
        if normalized != str(MemoryType.SEMANTIC):
            return normalized
        inferred = self._infer_memory_type(text=text, agent_id=agent_id, run_id=run_id, role=role)
        return inferred or normalized

    def _infer_memory_type(
        self,
        *,
        text: str,
        agent_id: str | None,
        run_id: str | None,
        role: str | None,
    ) -> str | None:
        lowered = text.lower()
        policy = self.config.memory_policy
        if any(cue in lowered or cue in text for cue in policy.preference_cues):
            return str(MemoryType.PREFERENCE)
        if any(cue in lowered or cue in text for cue in policy.relationship_cues):
            return str(MemoryType.RELATIONSHIP_SUMMARY)
        if any(cue in lowered or cue in text for cue in policy.profile_cues):
            return str(MemoryType.PROFILE)
        if run_id and any(cue in lowered or cue in text for cue in policy.episodic_cues):
            return str(MemoryType.EPISODIC)
        if any(cue in lowered or cue in text for cue in policy.procedural_cues):
            return str(MemoryType.PROCEDURAL)
        if agent_id and role == "assistant" and any(cue in lowered or cue in text for cue in ("should", "需要", "先", "然后")):
            return str(MemoryType.PROCEDURAL)
        return None

    def _extract_candidates(self, messages: list[NormalizedMessage]) -> list[str]:
        candidates: list[str] = []
        for message in messages:
            role = message.role
            if role not in {"user", "assistant", "system"}:
                continue
            for sentence in split_sentences(message.content):
                cleaned = sentence.strip()
                if 4 <= len(cleaned) <= 280 and cleaned not in candidates:
                    candidates.append(cleaned)
        return candidates[:8]

    def _promote_memory_row(self, item: dict[str, Any] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        metadata = dict(item.get("metadata") or {})
        for field in ("actor_id", "role", "session_id", "user_id", "agent_id", "run_id"):
            if field not in item or item.get(field) is None:
                if field in metadata:
                    item[field] = metadata[field]
        return item
