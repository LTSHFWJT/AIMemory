from __future__ import annotations

import time

from aimemory.core.capabilities import capability_dict


class SessionMemoryPromoterWorker:
    def __init__(self, memory_service):
        self.memory_service = memory_service

    def run_once(self, session_id: str, **kwargs) -> dict:
        return self.memory_service.promote_session_memories(session_id=session_id, **kwargs)

    def run_forever(self, session_ids: list[str], poll_interval: float = 5.0, **kwargs) -> None:
        while True:
            for session_id in session_ids:
                self.run_once(session_id=session_id, **kwargs)
            time.sleep(poll_interval)

    def describe_capabilities(self) -> dict:
        return capability_dict(
            category="worker",
            provider="session-promoter",
            features={
                "session_promotion": True,
                "scope_aware": True,
                "background_platform": False,
            },
            notes=["local worker for promoting session memories into long-term memory"],
        )
