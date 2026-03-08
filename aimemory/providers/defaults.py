from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aimemory.core.capabilities import capability_dict
from aimemory.core.governance import (
    governance_scope_profile,
    governance_scope_rules,
    memory_type_policy_profile,
    resolve_strategy_scope,
)
from aimemory.core.text import cosine_similarity, extract_keywords, hash_embedding, normalize_text, split_sentences
from aimemory.domains.memory.models import MemoryType
from aimemory.memory_intelligence.models import (
    FactCandidate,
    MemoryAction,
    MemoryActionType,
    MemoryScopeContext,
    MessagePart,
    NeighborMemory,
    NormalizedMessage,
)
from aimemory.memory_intelligence.policies import MemoryPolicy


QUERY_ARCHIVE_CUES = ("archive", "归档", "历史", "更早", "过去", "older", "past")
QUERY_EXECUTION_CUES = ("run", "task", "checkpoint", "step", "执行", "步骤", "任务", "workflow")
QUERY_INTERACTION_CUES = ("session", "会话", "刚才", "上一轮", "上下文", "recent")


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def infer_query_profile(query: str, *, context: MemoryScopeContext, policy: MemoryPolicy) -> dict[str, Any]:
    lowered = query.lower()
    focus_memory_types: list[str]
    query_mode = "semantic"

    if _contains_any(lowered, policy.preference_query_cues):
        query_mode = "preference"
        focus_memory_types = [str(MemoryType.PREFERENCE), str(MemoryType.PROFILE), str(MemoryType.RELATIONSHIP_SUMMARY)]
    elif _contains_any(lowered, policy.relationship_query_cues):
        query_mode = "relationship"
        focus_memory_types = [str(MemoryType.RELATIONSHIP_SUMMARY), str(MemoryType.PROFILE), str(MemoryType.PREFERENCE)]
    elif _contains_any(lowered, policy.profile_query_cues):
        query_mode = "profile"
        focus_memory_types = [str(MemoryType.PROFILE), str(MemoryType.RELATIONSHIP_SUMMARY), str(MemoryType.PREFERENCE)]
    elif _contains_any(lowered, policy.procedural_query_cues):
        query_mode = "procedural"
        focus_memory_types = [str(MemoryType.PROCEDURAL), str(MemoryType.SEMANTIC)]
    elif _contains_any(lowered, policy.episodic_query_cues) or _contains_any(lowered, QUERY_EXECUTION_CUES):
        query_mode = "episodic"
        focus_memory_types = [str(MemoryType.EPISODIC), str(MemoryType.PROCEDURAL), str(MemoryType.SEMANTIC)]
    else:
        focus_memory_types = [
            str(MemoryType.SEMANTIC),
            str(MemoryType.PROCEDURAL),
            str(MemoryType.PREFERENCE),
            str(MemoryType.PROFILE),
            str(MemoryType.RELATIONSHIP_SUMMARY),
            str(MemoryType.EPISODIC),
        ]

    needs_archive = _contains_any(lowered, QUERY_ARCHIVE_CUES)
    needs_execution = _contains_any(lowered, QUERY_EXECUTION_CUES)
    needs_interaction = bool(context.session_id) and (
        _contains_any(lowered, policy.continuity_cues) or _contains_any(lowered, QUERY_INTERACTION_CUES) or query_mode == "episodic"
    )
    needs_agent_memory = bool(context.agent_id) and query_mode in {"procedural", "episodic"}
    needs_run_memory = bool(context.run_id) and query_mode == "episodic"

    if needs_run_memory:
        strategy_scope = "run"
    elif needs_agent_memory:
        strategy_scope = "agent"
    else:
        strategy_scope = "user"

    if query_mode in {"preference", "profile", "relationship", "procedural"}:
        preferred_scope = "long-term"
    elif needs_interaction or needs_run_memory:
        preferred_scope = "session"
    else:
        preferred_scope = "session" if context.session_id and _contains_any(lowered, policy.continuity_cues) else "long-term"

    handoff_domains: list[str] = []
    if needs_interaction:
        handoff_domains.append("interaction")
    if needs_execution:
        handoff_domains.append("execution")
    if needs_archive:
        handoff_domains.append("archive")
    if query_mode == "procedural":
        handoff_domains.append("skill")

    return {
        "query_mode": query_mode,
        "focus_memory_types": focus_memory_types,
        "preferred_scope": preferred_scope,
        "strategy_scope": strategy_scope,
        "needs_interaction": needs_interaction,
        "needs_execution": needs_execution,
        "needs_archive": needs_archive,
        "handoff_domains": handoff_domains,
    }


class NoopLLMProvider:
    def generate(self, messages: list[dict[str, Any]], *, response_format: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"messages": messages, "response_format": response_format}

    def describe_capabilities(self) -> dict[str, Any]:
        return capability_dict(
            category="llm",
            provider="noop",
            features={
                "generation": False,
                "structured_output": False,
                "remote_model": False,
            },
            notes=["placeholder provider for lightweight local mode"],
        )


class TextOnlyVisionProcessor:
    def normalize(self, messages: Any) -> list[NormalizedMessage]:
        if isinstance(messages, str):
            return [NormalizedMessage(role="user", content=messages, parts=[MessagePart(kind="text", text=messages)])]
        if isinstance(messages, dict):
            return [self._normalize_message(messages)]
        if not isinstance(messages, list):
            raise TypeError("messages must be str, dict, or list[dict]")
        return [self._normalize_message(message) for message in messages]

    def _normalize_message(self, message: dict[str, Any]) -> NormalizedMessage:
        role = message.get("role", "user")
        metadata = dict(message.get("metadata") or {})
        actor_id = message.get("name") or metadata.get("actor_id")
        content = message.get("content")
        if isinstance(content, str):
            return NormalizedMessage(role=role, content=content, actor_id=actor_id, metadata=metadata, parts=[MessagePart(kind="text", text=content)])

        parts: list[MessagePart] = []
        texts: list[str] = []
        omitted_parts: list[str] = []

        if isinstance(content, dict):
            extracted = str(content.get("text") or content.get("content") or "")
            if extracted:
                texts.append(extracted)
                parts.append(MessagePart(kind=content.get("type", "text"), text=extracted, payload=content))
            else:
                omitted_parts.append(content.get("type", "object"))
                parts.append(MessagePart(kind=content.get("type", "object"), payload=content))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                    parts.append(MessagePart(kind="text", text=item, payload=item))
                    continue
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("content") or "")
                    kind = str(item.get("type", "object"))
                    if text:
                        texts.append(text)
                        parts.append(MessagePart(kind=kind, text=text, payload=item))
                    else:
                        omitted_parts.append(kind)
                        parts.append(MessagePart(kind=kind, payload=item))
        else:
            texts.append(str(content or ""))
            parts.append(MessagePart(kind="text", text=str(content or ""), payload=content))

        if omitted_parts:
            metadata["omitted_modalities"] = omitted_parts
        return NormalizedMessage(role=role, content=" ".join(part for part in texts if part).strip(), actor_id=actor_id, metadata=metadata, parts=parts)

    def describe_capabilities(self) -> dict[str, Any]:
        return capability_dict(
            category="vision",
            provider="text-only",
            features={
                "text_normalization": True,
                "multimodal_placeholder": True,
                "image_understanding": False,
            },
            notes=["non-text modalities are preserved as metadata placeholders"],
        )


class RuleBasedFactExtractor:
    def extract(
        self,
        messages: list[NormalizedMessage],
        *,
        context: MemoryScopeContext,
        policy: MemoryPolicy,
        memory_type: str | None = None,
    ) -> list[FactCandidate]:
        candidates: list[FactCandidate] = []
        seen: set[str] = set()
        for message in messages:
            if message.role in policy.ignored_roles:
                continue
            for sentence in split_sentences(message.content):
                text = sentence.strip()
                if not text:
                    continue
                if len(text) < policy.min_candidate_chars or len(text) > policy.max_candidate_chars:
                    continue
                lowered = text.lower()
                chosen_type, classification_reason = self._classify_memory_type(
                    text,
                    lowered,
                    policy,
                    context=context,
                    role=message.role,
                    explicit_type=memory_type,
                )
                if chosen_type is None:
                    continue
                normalized = normalize_text(text)
                if normalized in seen:
                    continue
                seen.add(normalized)
                metadata = {
                    **context.as_metadata(),
                    **message.metadata,
                    "keywords": extract_keywords(text),
                    "source_role": message.role,
                    "classification_reason": classification_reason,
                }
                if message.actor_id:
                    metadata["actor_id"] = message.actor_id
                strategy_scope = resolve_strategy_scope(
                    chosen_type,
                    agent_id=context.agent_id,
                    run_id=context.run_id,
                    role=message.role,
                    metadata=metadata,
                    text=text,
                )
                metadata["strategy_scope"] = strategy_scope
                candidates.append(
                    FactCandidate(
                        text=text,
                        memory_type=chosen_type,
                        confidence=self._confidence_for(text, chosen_type, policy),
                        importance=self._importance_for(text, chosen_type, policy, strategy_scope=strategy_scope),
                        metadata=metadata,
                    )
                )
        candidates.sort(key=lambda item: (item.importance, item.confidence, len(item.text)), reverse=True)
        return candidates[: policy.max_candidates]

    def _classify_memory_type(
        self,
        text: str,
        lowered: str,
        policy: MemoryPolicy,
        *,
        context: MemoryScopeContext,
        role: str,
        explicit_type: str | None,
    ) -> tuple[str | None, str]:
        if explicit_type:
            return str(explicit_type), "explicit"
        if policy.extract_preferences and any(cue in lowered or cue in text for cue in policy.preference_cues):
            return str(MemoryType.PREFERENCE), "preference-cue"
        if policy.extract_relationships and any(cue in lowered or cue in text for cue in policy.relationship_cues):
            return str(MemoryType.RELATIONSHIP_SUMMARY), "relationship-cue"
        if any(token in lowered or token in text for token in policy.profile_cues):
            return str(MemoryType.PROFILE), "profile-cue"
        if policy.extract_episodic and (
            (context.run_id and any(cue in lowered or cue in text for cue in policy.episodic_cues))
            or (context.run_id and any(cue in lowered or cue in text for cue in ("正在", "完成", "checkpoint", "run")))
        ):
            return str(MemoryType.EPISODIC), "run-episodic-cue"
        if policy.extract_procedural and (
            any(cue in lowered or cue in text for cue in policy.procedural_cues)
            or (context.agent_id and role == "assistant" and any(token in lowered or token in text for token in ("建议", "should", "需要", "先", "然后")))
        ):
            return str(MemoryType.PROCEDURAL), "procedural-cue"
        if policy.extract_episodic and any(cue in lowered or cue in text for cue in policy.episodic_cues):
            return str(MemoryType.EPISODIC), "episodic-cue"
        if policy.extract_facts:
            return str(MemoryType.SEMANTIC), "semantic-fallback"
        return None, "ignored"

    def _importance_for(self, text: str, memory_type: str, policy: MemoryPolicy, *, strategy_scope: str) -> float:
        importance = 0.55
        if memory_type == str(MemoryType.PREFERENCE):
            importance = 0.82
        elif memory_type == str(MemoryType.RELATIONSHIP_SUMMARY):
            importance = 0.79
        elif memory_type == str(MemoryType.PROCEDURAL):
            importance = 0.76
        elif memory_type == str(MemoryType.PROFILE):
            importance = 0.78
        elif memory_type == str(MemoryType.EPISODIC):
            importance = 0.63
        elif memory_type == str(MemoryType.SEMANTIC):
            importance = 0.68
        if len(text) >= 40:
            importance += 0.05
        lowered = text.lower()
        if any(cue in lowered or cue in text for cue in policy.update_cues + policy.delete_cues):
            importance += 0.03
        importance += float(governance_scope_profile(strategy_scope)["importance_bias"])
        return min(1.0, importance)

    def _confidence_for(self, text: str, memory_type: str, policy: MemoryPolicy) -> float:
        confidence = 0.64
        lowered = text.lower()
        if memory_type == str(MemoryType.PREFERENCE):
            confidence += 0.12
        elif memory_type == str(MemoryType.RELATIONSHIP_SUMMARY):
            confidence += 0.08
        elif memory_type == str(MemoryType.PROCEDURAL):
            confidence += 0.08
        elif memory_type == str(MemoryType.PROFILE):
            confidence += 0.1
        elif memory_type == str(MemoryType.EPISODIC):
            confidence += 0.06
        if any(cue in lowered or cue in text for cue in policy.update_cues):
            confidence += 0.05
        if len(extract_keywords(text)) >= 4:
            confidence += 0.04
        return min(1.0, confidence)

    def describe_capabilities(self) -> dict[str, Any]:
        return capability_dict(
            category="extractor",
            provider="rule",
            features={
                "rule_based": True,
                "memory_type_inference": True,
                "strategy_scope_inference": True,
                "llm_required": False,
            },
        )


class EvidenceMemoryPlanner:
    def plan(
        self,
        candidate: FactCandidate,
        neighbors: list[NeighborMemory],
        *,
        context: MemoryScopeContext,
        policy: MemoryPolicy,
    ) -> list[MemoryAction]:
        if not neighbors:
            return [
                MemoryAction(
                    action_type=MemoryActionType.ADD,
                    candidate=candidate,
                    reason="no-neighbor",
                    confidence=candidate.confidence,
                    evidence={"matched_neighbors": 0},
                )
            ]

        targetable_neighbors = [neighbor for neighbor in neighbors if neighbor.metadata.get("targetable", True)]
        if not targetable_neighbors:
            return [
                MemoryAction(
                    action_type=MemoryActionType.ADD,
                    candidate=candidate,
                    reason="no-targetable-neighbor",
                    confidence=candidate.confidence,
                    evidence={
                        "matched_neighbors": len(neighbors),
                        "targetable_neighbors": 0,
                    },
                )
            ]

        evidence_rows = [self._evaluate(candidate, neighbor, policy) for neighbor in targetable_neighbors]
        evidence_rows.sort(key=lambda item: item["support_score"], reverse=True)
        best = evidence_rows[0]
        neighbor = best["neighbor"]
        action_type, reason, confidence = self._resolve_action(candidate, best, policy)
        return [
            MemoryAction(
                action_type=action_type,
                candidate=candidate,
                target_id=neighbor.id if action_type != MemoryActionType.ADD else None,
                previous_text=neighbor.text if action_type in {MemoryActionType.UPDATE, MemoryActionType.DELETE, MemoryActionType.NONE} else None,
                reason=reason,
                confidence=confidence,
                evidence=self._evidence_payload(best),
            )
        ]

    def _evaluate(self, candidate: FactCandidate, neighbor: NeighborMemory, policy: MemoryPolicy) -> dict[str, Any]:
        strategy = self._strategy(candidate, None, policy)
        candidate_keywords = set(candidate.metadata.get("keywords") or extract_keywords(candidate.text))
        neighbor_keywords = set(neighbor.metadata.get("keywords") or extract_keywords(neighbor.text))
        normalized_candidate = normalize_text(candidate.text)
        normalized_neighbor = normalize_text(neighbor.text)
        embedding_score = max(0.0, cosine_similarity(hash_embedding(candidate.text), hash_embedding(neighbor.text)))
        keyword_score = self._jaccard(candidate_keywords, neighbor_keywords)
        character_score = self._character_overlap(candidate.text, neighbor.text)
        exact_match = normalized_candidate == normalized_neighbor
        containment = normalized_candidate in normalized_neighbor or normalized_neighbor in normalized_candidate
        type_match = 1.0 if not neighbor.memory_type or neighbor.memory_type == candidate.memory_type else 0.0
        recall_source = str(neighbor.metadata.get("recall_source") or "")
        recall_bonus = 0.05 if recall_source == "primary" else 0.0
        retrieval_score = float(neighbor.score)

        support_score = min(
            1.0,
            (0.32 * retrieval_score)
            + (0.28 * embedding_score)
            + (0.18 * keyword_score)
            + (0.1 * character_score)
            + (0.07 * type_match)
            + (0.05 if containment else 0.0)
            + recall_bonus,
        )

        lowered = candidate.text.lower()
        update_cue = any(cue in lowered or cue in candidate.text for cue in policy.update_cues)
        delete_cue = any(cue in lowered or cue in candidate.text for cue in policy.delete_cues)
        negation_cue = any(cue in lowered or cue in candidate.text for cue in policy.negation_cues)
        informativeness_gain = max(0.0, len(candidate.text) - len(neighbor.text)) / max(1, len(candidate.text))
        replacement_signal = 1.0 if update_cue or ("instead" in lowered) or ("改成" in candidate.text) else 0.0
        slot_match = self._slot_match(candidate, neighbor, keyword_score, type_match)
        if strategy["prefer_slot_update"] and slot_match:
            replacement_signal = max(replacement_signal, 0.75)

        duplicate_score = min(1.0, support_score + (0.18 if exact_match else 0.0) + (0.08 if containment else 0.0))
        update_score = min(1.0, (support_score * 0.72) + (0.2 if replacement_signal else 0.0) + (0.08 * informativeness_gain))
        delete_score = min(1.0, (support_score * 0.58) + (0.28 if delete_cue else 0.0) + (0.14 if negation_cue else 0.0))
        merge_score = min(1.0, (support_score * 0.8) + (0.12 * informativeness_gain) + (0.08 * type_match))

        if slot_match:
            duplicate_score = min(1.0, duplicate_score + strategy["slot_duplicate_bonus"])
            update_score = min(1.0, update_score + strategy["slot_update_bonus"])
            merge_score = min(1.0, merge_score + strategy["slot_merge_bonus"])
        if strategy["prefer_richer_merge"] and informativeness_gain >= 0.08:
            merge_score = min(1.0, merge_score + 0.08)
        if not strategy["allow_delete"]:
            delete_score *= 0.45

        return {
            "neighbor": neighbor,
            "support_score": round(support_score, 6),
            "duplicate_score": round(duplicate_score, 6),
            "update_score": round(update_score, 6),
            "delete_score": round(delete_score, 6),
            "merge_score": round(merge_score, 6),
            "retrieval_score": round(retrieval_score, 6),
            "embedding_score": round(embedding_score, 6),
            "keyword_score": round(keyword_score, 6),
            "character_score": round(character_score, 6),
            "informativeness_gain": round(informativeness_gain, 6),
            "exact_match": exact_match,
            "containment": containment,
            "type_match": bool(type_match),
            "slot_match": slot_match,
            "update_cue": update_cue,
            "delete_cue": delete_cue,
            "negation_cue": negation_cue,
            "recall_source": recall_source,
            "strategy": strategy["name"],
        }

    def _resolve_action(self, candidate: FactCandidate, best: dict[str, Any], policy: MemoryPolicy) -> tuple[MemoryActionType, str, float]:
        strategy = self._strategy(candidate, best, policy)
        support_score = float(best["support_score"])
        duplicate_score = float(best["duplicate_score"])
        update_score = float(best["update_score"])
        delete_score = float(best["delete_score"])
        merge_score = float(best["merge_score"])
        exact_match = bool(best["exact_match"])
        containment = bool(best["containment"])
        slot_match = bool(best.get("slot_match"))
        update_cue = bool(best["update_cue"])
        delete_cue = bool(best["delete_cue"])
        informativeness_gain = float(best["informativeness_gain"])

        if delete_cue and strategy["allow_delete"] and delete_score >= strategy["delete_floor"]:
            return MemoryActionType.DELETE, f"{strategy['name']}-delete", delete_score

        if exact_match:
            return MemoryActionType.NONE, f"{strategy['name']}-duplicate", duplicate_score

        if (update_cue or (strategy["prefer_slot_update"] and slot_match)) and support_score >= strategy["support_floor"] and update_score >= strategy["update_floor"]:
            return MemoryActionType.UPDATE, f"{strategy['name']}-update", update_score

        if merge_score >= strategy["merge_floor"] and (containment or slot_match or informativeness_gain >= strategy["merge_gain_floor"]):
            return MemoryActionType.UPDATE, f"{strategy['name']}-merge", merge_score

        if duplicate_score >= strategy["duplicate_floor"]:
            return MemoryActionType.NONE, f"{strategy['name']}-duplicate", duplicate_score

        if support_score >= strategy["containment_floor"] and (containment or (slot_match and strategy["prefer_slot_update"])):
            return MemoryActionType.NONE, f"{strategy['name']}-containment", support_score

        return MemoryActionType.ADD, "new-fact", max(candidate.confidence, 0.5)

    def _type_strategy(self, candidate: FactCandidate, policy: MemoryPolicy) -> dict[str, Any]:
        strategy = {
            "name": "semantic",
            "allow_delete": policy.allow_delete,
            "duplicate_floor": policy.duplicate_threshold,
            "update_floor": policy.update_min_score,
            "merge_floor": policy.merge_threshold,
            "delete_floor": max(policy.delete_min_score, policy.conflict_threshold),
            "support_floor": max(0.34, policy.update_min_score * 0.75),
            "containment_floor": policy.candidate_merge_threshold,
            "merge_gain_floor": 0.12,
            "prefer_slot_update": False,
            "prefer_richer_merge": False,
            "slot_update_bonus": 0.0,
            "slot_merge_bonus": 0.0,
            "slot_duplicate_bonus": 0.0,
        }
        if candidate.memory_type == str(MemoryType.PREFERENCE):
            strategy.update(
                name="preference",
                duplicate_floor=max(0.9, policy.duplicate_threshold - 0.05),
                update_floor=max(0.48, policy.update_min_score - 0.08),
                merge_floor=max(0.76, policy.merge_threshold - 0.1),
                delete_floor=max(0.74, policy.delete_min_score - 0.04),
                support_floor=max(0.32, policy.update_min_score * 0.68),
                containment_floor=max(0.58, policy.candidate_merge_threshold - 0.08),
                prefer_slot_update=True,
                slot_update_bonus=0.12,
                slot_merge_bonus=0.08,
                slot_duplicate_bonus=0.05,
            )
        elif candidate.memory_type == str(MemoryType.RELATIONSHIP_SUMMARY):
            strategy.update(
                name="relationship-summary",
                duplicate_floor=max(0.88, policy.duplicate_threshold - 0.06),
                update_floor=max(0.46, policy.update_min_score - 0.08),
                merge_floor=max(0.74, policy.merge_threshold - 0.12),
                delete_floor=max(0.76, policy.delete_min_score - 0.02),
                support_floor=max(0.3, policy.update_min_score * 0.66),
                containment_floor=max(0.56, policy.candidate_merge_threshold - 0.08),
                prefer_slot_update=True,
                slot_update_bonus=0.1,
                slot_merge_bonus=0.08,
                slot_duplicate_bonus=0.04,
            )
        elif candidate.memory_type == str(MemoryType.PROFILE):
            strategy.update(
                name="profile",
                duplicate_floor=max(0.88, policy.duplicate_threshold - 0.08),
                update_floor=max(0.44, policy.update_min_score - 0.1),
                merge_floor=max(0.74, policy.merge_threshold - 0.12),
                delete_floor=max(0.78, policy.delete_min_score),
                support_floor=max(0.3, policy.update_min_score * 0.64),
                containment_floor=max(0.54, policy.candidate_merge_threshold - 0.1),
                prefer_slot_update=True,
                slot_update_bonus=0.14,
                slot_merge_bonus=0.06,
                slot_duplicate_bonus=0.06,
            )
        elif candidate.memory_type == str(MemoryType.PROCEDURAL):
            strategy.update(
                name="procedural",
                allow_delete=False,
                duplicate_floor=min(0.99, policy.duplicate_threshold + 0.01),
                update_floor=max(0.5, policy.update_min_score - 0.04),
                merge_floor=max(0.7, policy.merge_threshold - 0.18),
                support_floor=max(0.34, policy.update_min_score * 0.7),
                containment_floor=max(0.62, policy.candidate_merge_threshold - 0.02),
                merge_gain_floor=0.08,
                prefer_slot_update=True,
                prefer_richer_merge=True,
                slot_update_bonus=0.08,
                slot_merge_bonus=0.14,
                slot_duplicate_bonus=0.03,
            )
        elif candidate.memory_type == str(MemoryType.EPISODIC):
            strategy.update(
                name="episodic",
                allow_delete=False,
                duplicate_floor=max(0.82, policy.duplicate_threshold - 0.12),
                update_floor=max(0.46, policy.update_min_score - 0.08),
                merge_floor=max(0.68, policy.merge_threshold - 0.2),
                delete_floor=max(0.9, policy.delete_min_score + 0.05),
                support_floor=max(0.28, policy.update_min_score * 0.62),
                containment_floor=max(0.5, policy.candidate_merge_threshold - 0.12),
                merge_gain_floor=0.05,
                prefer_richer_merge=True,
                slot_update_bonus=0.04,
                slot_merge_bonus=0.1,
                slot_duplicate_bonus=0.05,
            )
        return strategy

    def _strategy(self, candidate: FactCandidate, best: dict[str, Any] | None, policy: MemoryPolicy) -> dict[str, Any]:
        strategy = self._type_strategy(candidate, policy)
        strategy_scope = str(candidate.metadata.get("strategy_scope") or "user")
        scope_profile = governance_scope_profile(strategy_scope)
        strategy["update_floor"] = max(0.28, float(strategy["update_floor"]) - float(scope_profile["update_bias"]))
        strategy["merge_floor"] = max(0.58, float(strategy["merge_floor"]) - float(scope_profile["merge_bias"]))
        strategy["support_floor"] = max(0.22, float(strategy["support_floor"]) - (float(scope_profile["update_bias"]) * 0.5))
        strategy["delete_floor"] = max(0.42, float(strategy["delete_floor"]) + max(0.0, float(scope_profile["retention_bias"])))
        strategy["containment_floor"] = max(0.4, float(strategy["containment_floor"]) - (float(scope_profile["update_bias"]) * 0.4))
        strategy["merge_gain_floor"] = max(0.04, float(strategy["merge_gain_floor"]) - (float(scope_profile["merge_bias"]) * 0.2))
        if strategy_scope == "agent":
            strategy["prefer_richer_merge"] = True
        elif strategy_scope == "run":
            strategy["duplicate_floor"] = max(0.78, float(strategy["duplicate_floor"]) - 0.06)
            strategy["containment_floor"] = max(0.32, float(strategy["containment_floor"]) - 0.08)
        if best is not None:
            best["strategy_scope"] = strategy_scope
        return strategy

    def _slot_match(self, candidate: FactCandidate, neighbor: NeighborMemory, keyword_score: float, type_match: float) -> bool:
        if not type_match:
            return False
        if candidate.memory_type in {str(MemoryType.PREFERENCE), str(MemoryType.PROFILE)}:
            return keyword_score >= 0.22
        if candidate.memory_type == str(MemoryType.RELATIONSHIP_SUMMARY):
            return keyword_score >= 0.16
        if candidate.memory_type == str(MemoryType.PROCEDURAL):
            return keyword_score >= 0.18
        if candidate.memory_type == str(MemoryType.EPISODIC):
            candidate_run_id = candidate.metadata.get("run_id")
            neighbor_run_id = neighbor.metadata.get("run_id")
            if candidate_run_id and neighbor_run_id and candidate_run_id == neighbor_run_id:
                return keyword_score >= 0.12
            return keyword_score >= 0.24
        return False

    def _evidence_payload(self, best: dict[str, Any]) -> dict[str, Any]:
        return {
            "target_id": best["neighbor"].id,
            "support_score": best["support_score"],
            "duplicate_score": best["duplicate_score"],
            "update_score": best["update_score"],
            "delete_score": best["delete_score"],
            "merge_score": best["merge_score"],
            "retrieval_score": best["retrieval_score"],
            "embedding_score": best["embedding_score"],
            "keyword_score": best["keyword_score"],
            "character_score": best["character_score"],
            "informativeness_gain": best["informativeness_gain"],
            "recall_source": best["recall_source"],
            "type_match": best["type_match"],
            "slot_match": best.get("slot_match", False),
            "strategy": best.get("strategy", "semantic"),
            "strategy_scope": best.get("strategy_scope", "user"),
        }

    def _character_overlap(self, left: str, right: str) -> float:
        left_chars = {char for char in left if char.strip() and char.isalnum()}
        right_chars = {char for char in right if char.strip() and char.isalnum()}
        if not left_chars or not right_chars:
            return 0.0
        return len(left_chars & right_chars) / max(1, len(left_chars | right_chars))

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / max(1, len(left | right))

    def describe_capabilities(self) -> dict[str, Any]:
        return capability_dict(
            category="planner",
            provider="evidence",
            features={
                "rule_based": True,
                "evidence_planning": True,
                "type_specific_strategy": True,
                "scope_specific_strategy": True,
                "llm_required": False,
            },
        )


class HeuristicMemoryPlanner(EvidenceMemoryPlanner):
    pass


class RuleBasedReranker:
    def rerank(
        self,
        query: str,
        records: list[dict[str, Any]],
        *,
        domain: str,
        context: MemoryScopeContext,
        policy: MemoryPolicy | None = None,
    ) -> list[dict[str, Any]]:
        policy = policy or MemoryPolicy()
        ranked: list[dict[str, Any]] = []
        query_profile = infer_query_profile(query, context=context, policy=policy)
        query_lower = query.lower()
        for record in records:
            updated = dict(record)
            score = float(updated.get("score", 0.0))
            metadata = dict(updated.get("metadata") or {})

            if domain == "memory":
                score += float(updated.get("importance", 0.5)) * 0.15
                if updated.get("scope") == "session" and any(cue in query_lower for cue in policy.continuity_cues):
                    score += 0.12
                if updated.get("scope") == "long-term" and any(cue in query_lower for cue in policy.preference_query_cues + policy.fact_query_cues):
                    score += 0.08
                record_type = str(updated.get("memory_type") or MemoryType.SEMANTIC)
                if record_type in set(query_profile["focus_memory_types"]):
                    score += 0.08 + float(memory_type_policy_profile(record_type)["recall_bias"])
                if record_type == str(MemoryType.PREFERENCE) and any(cue in query_lower for cue in policy.preference_query_cues):
                    score += 0.12
                strategy_scope = str(metadata.get("strategy_scope") or "user")
                if strategy_scope == query_profile["strategy_scope"]:
                    score += 0.06
                if context.run_id and updated.get("run_id") == context.run_id:
                    score += 0.14
                elif context.run_id and strategy_scope == "run":
                    score -= 0.04
                if context.agent_id and updated.get("agent_id") == context.agent_id:
                    score += 0.1
                elif context.agent_id and strategy_scope == "agent":
                    score += 0.04
                if context.user_id and updated.get("user_id") == context.user_id and strategy_scope == "user":
                    score += 0.05
                graph_context = dict(updated.get("graph_context") or {})
                score += min(0.08, float(graph_context.get("relation_count", 0)) * 0.012)
                score += min(0.12, float(graph_context.get("matched_relation_count", 0)) * 0.04)
                score += min(0.08, float(graph_context.get("top_relation_score", 0.0)) * 0.08)
            elif domain == "skill" and updated.get("skill", {}).get("status") == "active":
                score += 0.08
            elif domain == "archive" and context.session_id and updated.get("session_id") == context.session_id:
                score += 0.06

            if context.actor_id and metadata.get("actor_id") == context.actor_id:
                score += 0.05
            if context.role and metadata.get("role") == context.role:
                score += 0.03

            score += self._recency_boost(updated.get("updated_at") or updated.get("created_at"))
            updated["score"] = round(score, 6)
            ranked.append(updated)

        ranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return ranked

    def _recency_boost(self, timestamp: str | None) -> float:
        if not timestamp:
            return 0.0
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if age_hours <= 6:
            return 0.07
        if age_hours <= 24:
            return 0.04
        if age_hours <= 24 * 7:
            return 0.02
        return 0.0

    def describe_capabilities(self) -> dict[str, Any]:
        return capability_dict(
            category="reranker",
            provider="rule",
            features={
                "rule_based": True,
                "graph_aware": True,
                "context_aware": True,
                "llm_required": False,
            },
        )


class VeryLiteRecallPlanner:
    def plan(
        self,
        query: str,
        *,
        context: MemoryScopeContext,
        policy: MemoryPolicy,
        preferred_scope: str | None = None,
        limit: int | None = None,
        auxiliary_limit: int | None = None,
        graph_enabled: bool = True,
    ) -> dict[str, Any]:
        query_profile = infer_query_profile(query, context=context, policy=policy)
        strategy_scope = str(query_profile["strategy_scope"])
        if preferred_scope is not None:
            primary_scope = preferred_scope
        else:
            primary_scope = str(query_profile["preferred_scope"])
        secondary_scope = "long-term" if primary_scope == "session" else "session"
        primary_limit = int(limit or policy.search_limit)
        secondary_limit = int(policy.auxiliary_search_limit if auxiliary_limit is None else auxiliary_limit)
        scope_rules = governance_scope_rules(strategy_scope)
        focus_memory_types = list(dict.fromkeys(query_profile["focus_memory_types"]))
        stages = [
            {
                "name": "primary",
                "scope": primary_scope,
                "limit": primary_limit,
                "targetable": True,
                "score_bias": 0.08 if primary_scope == "session" else 0.05,
                "memory_types": focus_memory_types,
                "strategy_scopes": [strategy_scope],
            }
        ]
        if secondary_limit > 0:
            stages.append(
                {
                    "name": "auxiliary",
                    "scope": secondary_scope,
                    "limit": secondary_limit,
                    "targetable": False,
                    "score_bias": 0.02 if secondary_scope == "long-term" else 0.0,
                    "memory_types": focus_memory_types[:2] if focus_memory_types else [],
                    "strategy_scopes": ["user", "agent", "run"],
                }
            )
        if query_profile["query_mode"] == "episodic" and context.session_id and secondary_limit > 0:
            stages.append(
                {
                    "name": "evidence",
                    "scope": "session",
                    "limit": max(1, secondary_limit - 1),
                    "targetable": False,
                    "score_bias": 0.06,
                    "memory_types": [str(MemoryType.EPISODIC), str(MemoryType.PROCEDURAL)],
                    "strategy_scopes": ["run", "agent"],
                }
            )
        return {
            "strategy_scope": strategy_scope,
            "strategy_name": f"{strategy_scope}-{query_profile['query_mode']}-{primary_scope}-first",
            "query_profile": query_profile,
            "graph_enrichment": bool(graph_enabled),
            "handoff_domains": list(dict.fromkeys(query_profile["handoff_domains"])),
            "policy_notes": list(scope_rules.get("notes", [])),
            "stages": stages,
        }

    def describe_capabilities(self) -> dict[str, Any]:
        return capability_dict(
            category="recall_planner",
            provider="lite",
            features={
                "multi_stage_recall": True,
                "scope_aware": True,
                "typed_recall": True,
                "scope_specific_stages": True,
                "domain_handoff_hints": True,
                "graph_hinting": True,
                "llm_required": False,
            },
        )
