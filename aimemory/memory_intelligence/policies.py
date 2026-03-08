from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MemoryPolicy:
    infer_by_default: bool = True
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_procedural: bool = True
    extract_relationships: bool = True
    extract_episodic: bool = True
    allow_delete: bool = True
    conflict_threshold: float = 0.72
    merge_threshold: float = 0.88
    duplicate_threshold: float = 0.96
    candidate_merge_threshold: float = 0.82
    update_min_score: float = 0.58
    delete_min_score: float = 0.82
    search_limit: int = 5
    auxiliary_search_limit: int = 3
    compression_turn_threshold: int = 14
    compression_preserve_recent_turns: int = 6
    cleanup_importance_threshold: float = 0.34
    cleanup_recent_score_ceiling: float = 0.08
    snapshot_keep_recent: int = 3
    session_health_snapshot_stale_hours: int = 24
    max_candidates: int = 8
    max_candidate_chars: int = 280
    min_candidate_chars: int = 4
    preference_cues: tuple[str, ...] = (
        "喜欢",
        "偏好",
        "习惯",
        "prefer",
        "favorite",
        "ideal",
        "希望",
        "倾向",
    )
    procedural_cues: tuple[str, ...] = (
        "步骤",
        "流程",
        "先",
        "然后",
        "最后",
        "how to",
        "workflow",
        "route",
        "router",
    )
    profile_cues: tuple[str, ...] = (
        "my name",
        "i am",
        "i'm",
        "我是",
        "我叫",
        "身份",
        "职业",
        "role",
    )
    episodic_cues: tuple[str, ...] = (
        "this run",
        "current run",
        "last run",
        "checkpoint",
        "executed",
        "执行",
        "本次 run",
        "当前 run",
        "刚刚",
        "刚才",
        "完成了",
        "发生了",
    )
    relationship_cues: tuple[str, ...] = (
        "teammate",
        "manager",
        "stakeholder",
        "customer",
        "partner",
        "friend",
        "colleague",
        "同事",
        "老板",
        "经理",
        "客户",
        "朋友",
        "团队",
        "合作方",
        "对接人",
    )
    update_cues: tuple[str, ...] = (
        "现在",
        "改成",
        "更新",
        "不再",
        "changed",
        "now",
        "instead",
        "from now on",
    )
    delete_cues: tuple[str, ...] = (
        "忘掉",
        "forget",
        "删除",
        "remove",
        "discard",
        "不用记",
    )
    negation_cues: tuple[str, ...] = (
        "不",
        "别",
        "不是",
        "不再",
        "don't",
        "not",
        "never",
    )
    continuity_cues: tuple[str, ...] = (
        "刚才",
        "上一轮",
        "this session",
        "session",
        "刚刚",
    )
    preference_query_cues: tuple[str, ...] = (
        "喜欢",
        "偏好",
        "preference",
        "prefer",
        "style",
        "回复方式",
    )
    profile_query_cues: tuple[str, ...] = (
        "是谁",
        "身份",
        "背景",
        "profile",
        "name",
        "about me",
    )
    procedural_query_cues: tuple[str, ...] = (
        "怎么做",
        "如何",
        "步骤",
        "流程",
        "procedure",
        "workflow",
        "how to",
    )
    episodic_query_cues: tuple[str, ...] = (
        "上一轮",
        "刚才",
        "run",
        "checkpoint",
        "执行到哪",
        "发生了什么",
        "what happened",
    )
    relationship_query_cues: tuple[str, ...] = (
        "谁负责",
        "谁是",
        "关系",
        "stakeholder",
        "teammate",
        "customer",
        "manager",
    )
    fact_query_cues: tuple[str, ...] = (
        "是谁",
        "什么",
        "where",
        "when",
        "fact",
        "信息",
    )
    ignored_roles: tuple[str, ...] = ("tool",)
