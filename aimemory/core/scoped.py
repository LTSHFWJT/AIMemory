from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aimemory.core.scope import CollaborationScope

if TYPE_CHECKING:
    from aimemory.core.facade import AIMemory


class ScopedAIMemory:
    def __init__(self, memory: "AIMemory", scope: CollaborationScope | dict[str, Any] | None = None):
        self.memory = memory
        self.scope = CollaborationScope.from_value(scope)

    def using(self, **scope_overrides: Any) -> "ScopedAIMemory":
        return ScopedAIMemory(self.memory, self.scope.merge(scope_overrides))

    def scope_dict(self) -> dict[str, str]:
        return self.scope.as_metadata()

    def _payload(self, kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.scope.apply_to_kwargs(kwargs)

    def add(self, messages, **kwargs: Any) -> dict[str, Any]:
        return self.memory.add(messages, **self._payload(kwargs))

    def create_session(self, user_id: str | None = None, session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._payload(kwargs)
        if user_id is not None:
            payload["user_id"] = user_id
        return self.memory.create_session(user_id=payload.pop("user_id", None), session_id=session_id, **payload)

    def append_turn(self, session_id: str, role: str, content: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.append_turn(session_id, role, content, **self._payload(kwargs))

    def memory_store(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.memory_store(text, **self._payload(kwargs))

    def remember_long_term(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.remember_long_term(text, **self._payload(kwargs))

    def remember_short_term(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.remember_short_term(text, **self._payload(kwargs))

    def memory_search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.memory_search(query, **self._payload(kwargs))

    def query(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.query(query, **self._payload(kwargs))

    def ingest_document(self, title: str, text: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.ingest_document(title, text, **self._payload(kwargs))

    def ingest_knowledge(self, title: str, text: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.ingest_knowledge(title, text, **self._payload(kwargs))

    def search_knowledge(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.search_knowledge(query, **self._payload(kwargs))

    def save_skill(self, name: str, description: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.save_skill(name, description, **self._payload(kwargs))

    def search_skills(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.search_skills(query, **self._payload(kwargs))

    def archive_session(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.archive_session(session_id, **self._payload(kwargs))

    def search_archive(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.search_archive(query, **self._payload(kwargs))

    def search_interaction(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.search_interaction(query, **self._payload(kwargs))

    def search_execution(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.search_execution(query, **self._payload(kwargs))

    def compress_session_context(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.memory.compress_session_context(session_id, **self._payload(kwargs))

    def storage_layout(self) -> dict[str, Any]:
        return self.memory.storage_layout(**self.scope.as_metadata())

    def create_mcp_adapter(self):
        return self.memory.create_mcp_adapter(scope=self.scope.as_metadata())
