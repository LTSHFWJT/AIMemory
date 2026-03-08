from __future__ import annotations

from typing import Any

from aimemory.core.text import extract_keywords
from aimemory.core.utils import json_dumps, make_id, utcnow_iso
from aimemory.domains.skill.models import SkillStatus
from aimemory.services.base import ServiceBase


class SkillService(ServiceBase):
    def register(
        self,
        name: str,
        description: str,
        owner_id: str | None = None,
        prompt_template: str | None = None,
        workflow: dict[str, Any] | str | None = None,
        schema: dict[str, Any] | None = None,
        version: str = "0.1.0",
        tools: list[str] | None = None,
        tests: list[dict[str, Any]] | None = None,
        topics: list[str] | None = None,
        assets: dict[str, Any] | None = None,
        status: str = SkillStatus.DRAFT,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        skill = self.db.fetch_one("SELECT * FROM skills WHERE name = ?", (name,))
        skill_id = skill["id"] if skill else make_id("skill")
        self.db.execute(
            """
            INSERT INTO skills(id, name, description, owner_id, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                owner_id = excluded.owner_id,
                status = excluded.status,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (skill_id, name, description, owner_id, str(status), json_dumps(metadata or {}), now, now),
        )

        asset_payload = {"assets": assets or {}, "topics": topics or [], "tools": tools or []}
        stored = self.object_store.put_text(json_dumps(asset_payload), object_type="skills", suffix=".json")
        object_row = self._persist_object(stored, mime_type="application/json", metadata={"skill_id": skill_id, "version": version})

        version_id = make_id("skillver")
        workflow_text = workflow if isinstance(workflow, str) else json_dumps(workflow or {})
        self.db.execute(
            """
            INSERT INTO skill_versions(id, skill_id, version, prompt_template, workflow, schema_json, object_id, changelog, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version_id, skill_id, version, prompt_template, workflow_text, json_dumps(schema or {}), object_row["id"], None, json_dumps(metadata or {}), now),
        )

        for tool_name in tools or []:
            self.db.execute(
                """
                INSERT INTO skill_bindings(id, skill_version_id, tool_name, binding_type, config, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (make_id("bind"), version_id, tool_name, "tool", json_dumps({}), now),
            )
        for test_case in tests or []:
            self.db.execute(
                """
                INSERT INTO skill_tests(id, skill_version_id, input_payload, expected_output, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    make_id("stest"),
                    version_id,
                    json_dumps(test_case.get("input", {})),
                    json_dumps(test_case.get("expected")),
                    json_dumps(test_case.get("metadata", {})),
                    now,
                ),
            )

        combined_text = "\n".join(part for part in [name, description, prompt_template or "", workflow_text or "", " ".join(topics or []), " ".join(tools or [])] if part)
        self.projection.enqueue(
            topic="skill.index",
            entity_type="skill_version",
            entity_id=version_id,
            action="upsert",
            payload={
                "record_id": version_id,
                "skill_id": skill_id,
                "version": version,
                "name": name,
                "description": description,
                "text": combined_text,
                "keywords": extract_keywords(combined_text),
                "tools": tools or [],
                "topics": topics or [],
                "metadata": metadata or {},
                "updated_at": now,
            },
        )
        if self.config.auto_project:
            self.projection.project_pending()
        return self.get_skill(skill_id)

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        skill = self._deserialize_row(self.db.fetch_one("SELECT * FROM skills WHERE id = ?", (skill_id,)))
        if skill is None:
            return None
        versions = self._deserialize_rows(self.db.fetch_all("SELECT * FROM skill_versions WHERE skill_id = ? ORDER BY created_at DESC", (skill_id,)))
        bindings = self._deserialize_rows(
            self.db.fetch_all(
                """
                SELECT sb.* FROM skill_bindings sb
                JOIN skill_versions sv ON sv.id = sb.skill_version_id
                WHERE sv.skill_id = ?
                ORDER BY sb.created_at ASC
                """,
                (skill_id,),
            ),
            ("config",),
        )
        tests = self._deserialize_rows(
            self.db.fetch_all(
                """
                SELECT st.* FROM skill_tests st
                JOIN skill_versions sv ON sv.id = st.skill_version_id
                WHERE sv.skill_id = ?
                ORDER BY st.created_at ASC
                """,
                (skill_id,),
            ),
            ("input_payload", "expected_output", "metadata"),
        )
        skill["versions"] = versions
        skill["bindings"] = bindings
        skill["tests"] = tests
        return skill

    def list_skills(self, status: str | None = None) -> dict[str, Any]:
        if status:
            rows = self.db.fetch_all("SELECT * FROM skills WHERE status = ? ORDER BY updated_at DESC", (status,))
        else:
            rows = self.db.fetch_all("SELECT * FROM skills ORDER BY updated_at DESC")
        return {"results": self._deserialize_rows(rows)}

    def activate_version(self, skill_id: str, version: str) -> dict[str, Any]:
        skill = self.get_skill(skill_id)
        if skill is None:
            raise ValueError(f"Skill `{skill_id}` does not exist.")
        match = next((item for item in skill["versions"] if item["version"] == version), None)
        if match is None:
            raise ValueError(f"Version `{version}` does not exist for skill `{skill_id}`.")
        self.db.execute("UPDATE skills SET status = ?, updated_at = ? WHERE id = ?", (str(SkillStatus.ACTIVE), utcnow_iso(), skill_id))
        return self.get_skill(skill_id)
