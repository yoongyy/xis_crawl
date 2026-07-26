from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from ..research_storage import ResearchStorage


@dataclass
class ActorConfig:
    source: str
    actor_id_env: str
    actor_id: str | None
    actor_name: str | None
    developer: str | None
    last_successful_test: str | None
    expected_input_schema: dict[str, Any] = field(default_factory=dict)
    expected_output_schema: dict[str, Any] = field(default_factory=dict)
    timestamp_field: str | None = None
    cost_estimate_usd: float | None = None
    known_limitations: list[str] = field(default_factory=list)
    approval_status: str = "unconfigured"
    input_templates: dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.actor_id)

    def template(self, purpose: str, **values: Any) -> dict[str, Any] | None:
        template = self.input_templates.get(purpose)
        if not isinstance(template, dict):
            return None
        return _render(template, values)


@dataclass
class ProviderSelection:
    source: str
    provider: str | None
    actor: ActorConfig | None
    reason: str


class ApifyActorRegistry:
    def __init__(
        self,
        path: Path = Path("config/apify_actors.yaml"),
        *,
        storage: ResearchStorage | None = None,
        direct_registry: dict[str, Any] | None = None,
    ) -> None:
        load_dotenv()
        self.path = path
        self.storage = storage or ResearchStorage()
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.defaults = (payload or {}).get("defaults") or {}
        self._actors = self._load_actors((payload or {}).get("sources") or {})
        self.direct_registry = direct_registry

    def sources(self) -> list[str]:
        return sorted(self._actors)

    def actor(self, source: str) -> ActorConfig | None:
        return self._actors.get(source)

    def effective_approval(self, source: str) -> str:
        actor = self.actor(source)
        if not actor or not actor.actor_id:
            return "unconfigured"
        row = self.storage.conn.execute(
            """SELECT status FROM apify_actor_tests
               WHERE source=? AND actor_id=? ORDER BY tested_at DESC,id DESC LIMIT 1""",
            (source, actor.actor_id),
        ).fetchone()
        if row and row[0] == "passed":
            return "approved"
        return actor.approval_status

    def can_execute(self, source: str) -> tuple[bool, str]:
        actor = self.actor(source)
        if not actor:
            return False, "source is absent from config/apify_actors.yaml"
        if not actor.actor_id:
            return False, f"{actor.actor_id_env} is missing"
        if not actor.actor_name or not actor.developer:
            return False, "Actor name/developer metadata is incomplete"
        if not actor.expected_input_schema or not actor.expected_output_schema:
            return False, "expected input/output schema metadata is incomplete"
        if not actor.timestamp_field:
            return False, "absolute timestamp field metadata is missing"
        if actor.cost_estimate_usd is None:
            return False, "Actor cost estimate metadata is missing"
        if self.effective_approval(source) != "approved":
            return False, "Actor has not passed a small test run"
        return True, "approved"

    def can_test(self, source: str) -> tuple[bool, str]:
        actor = self.actor(source)
        if not actor:
            return False, "source is absent from config/apify_actors.yaml"
        if not actor.actor_id:
            return False, f"{actor.actor_id_env} is missing"
        if not actor.actor_name or not actor.developer:
            return False, "Actor name/developer metadata is incomplete"
        if not actor.expected_input_schema or not actor.expected_output_schema:
            return False, "expected input/output schema metadata is incomplete"
        if not actor.timestamp_field:
            return False, "absolute timestamp field metadata is missing"
        if actor.cost_estimate_usd is None:
            return False, "Actor cost estimate metadata is missing"
        if actor.template("test", maximum_records=3) is None:
            return False, "small-test Actor input template is not configured"
        return True, "ready for small test"

    def select(
        self,
        source: str,
        *,
        preferred: str = "apify",
        allow_fallback: bool = True,
    ) -> ProviderSelection:
        if preferred == "apify":
            allowed, reason = self.can_execute(source)
            if allowed:
                return ProviderSelection(source, "apify", self.actor(source), reason)
            if not allow_fallback:
                return ProviderSelection(source, None, self.actor(source), reason)
            direct = self._direct_registry().get(source)
            if direct:
                health = direct.health_check()
                if health.get("status") in {"available", "optional"}:
                    return ProviderSelection(
                        source, "direct", self.actor(source),
                        f"Apify unavailable ({reason}); direct adapter available",
                    )
            return ProviderSelection(source, None, self.actor(source), reason)
        direct = self._direct_registry().get(source)
        return ProviderSelection(
            source,
            "direct" if direct else None,
            self.actor(source),
            "direct adapter selected" if direct else "direct adapter unavailable",
        )

    def save_test(
        self,
        *,
        source: str,
        actor_id: str,
        status: str,
        records_fetched: int,
        newest_verified_timestamp: datetime | None,
        cost_usd: float | None,
        schema_warnings: list[str],
        actor_run_id: str | None,
        error: str | None = None,
    ) -> None:
        tested_at = datetime.now(timezone.utc).isoformat()
        self.storage.conn.execute(
            """INSERT INTO apify_actor_tests(
               source,actor_id,tested_at,status,records_fetched,newest_verified_timestamp,
               cost_usd,schema_warnings_json,actor_run_id,error_message)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                source, actor_id, tested_at, status,
                records_fetched,
                newest_verified_timestamp.isoformat() if newest_verified_timestamp else None,
                cost_usd, json.dumps(schema_warnings), actor_run_id, error,
            ),
        )
        actor = self.actor(source)
        if actor and actor.actor_id == actor_id:
            self.storage.conn.execute(
                """INSERT INTO apify_actor_registry(
                   source,actor_id,actor_name,developer,last_successful_test,
                   expected_input_schema_json,expected_output_schema_json,timestamp_field,
                   cost_estimate_usd,known_limitations_json,approval_status,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source,actor_id) DO UPDATE SET
                   actor_name=excluded.actor_name,developer=excluded.developer,
                   last_successful_test=COALESCE(excluded.last_successful_test,apify_actor_registry.last_successful_test),
                   expected_input_schema_json=excluded.expected_input_schema_json,
                   expected_output_schema_json=excluded.expected_output_schema_json,
                   timestamp_field=excluded.timestamp_field,
                   cost_estimate_usd=excluded.cost_estimate_usd,
                   known_limitations_json=excluded.known_limitations_json,
                   approval_status=excluded.approval_status,updated_at=excluded.updated_at""",
                (
                    source, actor_id, actor.actor_name or "", actor.developer or "",
                    tested_at if status == "passed" else actor.last_successful_test,
                    json.dumps(actor.expected_input_schema, sort_keys=True),
                    json.dumps(actor.expected_output_schema, sort_keys=True),
                    actor.timestamp_field, actor.cost_estimate_usd,
                    json.dumps(actor.known_limitations),
                    "approved" if status == "passed" else "test_failed",
                    tested_at,
                ),
            )
        self.storage.conn.commit()

    def is_processed(self, workflow: str, source: str, source_id: str) -> bool:
        return bool(self.storage.conn.execute(
            """SELECT 1 FROM apify_processed_records
               WHERE workflow=? AND source=? AND source_id=?""",
            (workflow, source, source_id),
        ).fetchone())

    def save_collection_run(
        self,
        *,
        workflow: str,
        result: Any,
        records_accepted: int,
    ) -> None:
        cost = result.request_cost_metadata or {}
        self.storage.conn.execute(
            """INSERT OR REPLACE INTO apify_collection_runs(
               workflow,source,actor_id,actor_run_id,status,partial,
               records_fetched,records_accepted,estimated_cost_usd,actual_cost_usd,
               raw_json_path,started_at,finished_at,warnings_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                workflow, result.source, result.actor_id, result.actor_run_id,
                result.status, int(bool(result.partial)), len(result.items), records_accepted,
                cost.get("estimated_cost_usd"), cost.get("actual_cost_usd"),
                result.raw_json_path,
                result.started_at.isoformat() if result.started_at else None,
                result.finished_at.isoformat() if result.finished_at else None,
                json.dumps(result.warnings),
            ),
        )
        self.storage.conn.commit()

    def mark_processed(
        self,
        workflow: str,
        source: str,
        source_id: str,
        actor_run_id: str,
        published_at: datetime | None,
    ) -> None:
        self.storage.conn.execute(
            """INSERT OR IGNORE INTO apify_processed_records(
               workflow,source,source_id,actor_run_id,published_at,processed_at)
               VALUES(?,?,?,?,?,?)""",
            (
                workflow, source, source_id, actor_run_id,
                published_at.isoformat() if published_at else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.storage.conn.commit()

    def _load_actors(self, raw: dict[str, Any]) -> dict[str, ActorConfig]:
        actors: dict[str, ActorConfig] = {}
        for source, item in raw.items():
            item = item or {}
            env_name = str(item.get("actor_id_env") or f"APIFY_{source.upper()}_ACTOR_ID")
            actor_id = os.getenv(env_name) or item.get("actor_id")
            actors[source] = ActorConfig(
                source=source,
                actor_id_env=env_name,
                actor_id=str(actor_id) if actor_id else None,
                actor_name=item.get("actor_name"),
                developer=item.get("developer"),
                last_successful_test=item.get("last_successful_test"),
                expected_input_schema=item.get("expected_input_schema") or {},
                expected_output_schema=item.get("expected_output_schema") or {},
                timestamp_field=item.get("timestamp_field"),
                cost_estimate_usd=_float_or_none(item.get("cost_estimate_usd")),
                known_limitations=list(item.get("known_limitations") or []),
                approval_status=str(item.get("approval_status") or "unconfigured"),
                input_templates=item.get("input_templates") or {},
            )
        return actors

    def _direct_registry(self) -> dict[str, Any]:
        if self.direct_registry is None:
            from ..sources.registry import build_registry
            self.direct_registry = build_registry()
        return self.direct_registry


def _render(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, values) for item in value]
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return values.get(value[2:-2].strip())
    if isinstance(value, str):
        result = value
        for key, replacement in values.items():
            result = result.replace(f"{{{{{key}}}}}", str(replacement))
        return result
    return value


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
