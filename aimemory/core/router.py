from __future__ import annotations


class RetrievalRouter:
    def route(self, query: str, domain: str | None = None, session_id: str | None = None) -> list[str]:
        if domain and domain != "auto":
            return [domain]

        lowered = query.lower()
        routes: list[str] = []

        if any(keyword in lowered for keyword in ["文档", "知识库", "citation", "document", "docs", "manual"]):
            routes.append("knowledge")
        if any(keyword in lowered for keyword in ["skill", "技能", "workflow", "prompt", "工具", "tool"]):
            routes.append("skill")
        if any(keyword in lowered for keyword in ["archive", "归档", "历史", "之前", "old", "past"]):
            routes.append("archive")
        if any(keyword in lowered for keyword in ["run", "task", "checkpoint", "步骤", "执行"]):
            routes.append("execution")
        if session_id or any(keyword in lowered for keyword in ["session", "会话", "刚才", "上一轮"]):
            routes.append("interaction")

        routes.append("memory")
        ordered: list[str] = []
        for item in routes:
            if item not in ordered:
                ordered.append(item)
        return ordered
