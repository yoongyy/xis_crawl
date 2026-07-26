from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .deduplicator import text_hash
from .research_models import EvidenceFinding, PlannedQuery, ResearchPack, SourceRecord


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchStorage:
    def __init__(
        self,
        db_path: Path = Path("data/research.sqlite3"),
        migration_path: Path = Path("migrations/001_multisource_demand_engine.sql"),
    ) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        migration_paths = sorted(migration_path.parent.glob("*.sql")) if migration_path.name.startswith("001_") else [migration_path]
        for current_path in migration_paths:
            self.apply_migration(current_path)

    def apply_migration(self, path: Path) -> None:
        legacy_counts = self.legacy_counts()
        version = path.stem
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        seen = self.conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone()
        if not seen:
            safe_version = version.replace("'", "''")
            safe_time = now_iso().replace("'", "''")
            script = path.read_text(encoding="utf-8")
            self.conn.executescript(
                f"BEGIN IMMEDIATE;\n{script}\n"
                f"INSERT INTO schema_migrations(version,applied_at) VALUES('{safe_version}','{safe_time}');\n"
                "COMMIT;"
            )
        if legacy_counts != self.legacy_counts():
            raise RuntimeError("legacy table counts changed during additive migration")

    def legacy_counts(self) -> dict[str, int]:
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            table: self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("posts", "comments", "findings") if table in tables
        }

    def save_pack(self, pack: ResearchPack, path: Path) -> None:
        raw = json.dumps(pack.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        self.conn.execute(
            """INSERT INTO research_packs(slug,name,path,config_json,config_hash,updated_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name,path=excluded.path,
               config_json=excluded.config_json,config_hash=excluded.config_hash,updated_at=excluded.updated_at""",
            (pack.slug, pack.name, str(path), raw, hashlib.sha256(raw.encode()).hexdigest(), now_iso()),
        )
        self.conn.commit()

    def create_run(self, pack_slug: str, options: dict[str, Any]) -> int:
        cur = self.conn.execute(
            "INSERT INTO research_runs(pack_slug,started_at,status,options_json) VALUES(?,?,?,?)",
            (pack_slug, now_iso(), "running", json.dumps(options, default=str)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def latest_resumable_run(self, pack_slug: str) -> int | None:
        row = self.conn.execute(
            """SELECT id,status FROM research_runs WHERE pack_slug=?
               ORDER BY id DESC LIMIT 1""", (pack_slug,),
        ).fetchone()
        return (
            int(row[0])
            if row and row[1] in {"running", "interrupted", "failed"}
            else None
        )

    def finish_run(self, run_id: int, status: str, stopped_reason: str | None = None) -> None:
        self.conn.execute(
            "UPDATE research_runs SET ended_at=?,status=?,stopped_reason=? WHERE id=?",
            (now_iso(), status, stopped_reason, run_id),
        )
        self.conn.commit()

    def update_run_counts(self, run_id: int, discovered: int, valid: int, duplicates: int) -> None:
        self.conn.execute(
            """UPDATE research_runs SET records_discovered=?,records_valid=?,duplicate_records=?
               WHERE id=?""", (discovered, valid, duplicates, run_id),
        )
        self.conn.commit()

    def save_run_sources(self, run_id: int, statuses: dict[str, dict[str, Any]]) -> None:
        self.conn.executemany(
            """INSERT INTO research_run_sources(
               research_run_id,source,status,credential_required,detail,checked_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(research_run_id,source) DO UPDATE SET
               status=excluded.status,credential_required=excluded.credential_required,
               detail=excluded.detail,checked_at=excluded.checked_at""",
            [
                (
                    run_id, source, result.get("status", "unavailable"),
                    int(bool(result.get("credential_required"))),
                    str(result.get("detail") or ""), now_iso(),
                )
                for source, result in statuses.items()
            ],
        )
        self.conn.commit()

    def save_rate_limit(self, source: str, status: Any) -> None:
        self.conn.execute(
            """INSERT INTO source_rate_limits(source,remaining,reset_at,state,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(source) DO UPDATE SET remaining=excluded.remaining,
               reset_at=excluded.reset_at,state=excluded.state,updated_at=excluded.updated_at""",
            (source, status.remaining, status.reset_at, status.state, now_iso()),
        )
        self.conn.commit()

    def save_queries(self, run_id: int, queries: Iterable[PlannedQuery]) -> None:
        self.conn.executemany(
            """INSERT OR IGNORE INTO source_queries(
               research_run_id,source,query,purpose,priority,expected_value,maximum_results,
               freshness_window_days,api_calls_estimated) VALUES(?,?,?,?,?,?,?,?,?)""",
            [(run_id, q.source, q.query, q.purpose, q.priority, q.expected_value,
              q.maximum_results, q.freshness_window_days, 1) for q in queries],
        )
        self.conn.commit()

    def pending_queries(self, run_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM source_queries WHERE research_run_id=? AND status!='completed' ORDER BY priority,id",
            (run_id,),
        ))

    def finish_query(self, query_id: int, status: str, count: int = 0, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE source_queries SET status=?,records_returned=?,error_message=? WHERE id=?",
            (status, count, error, query_id),
        )
        self.conn.commit()

    def save_record(self, record: SourceRecord, run_id: int, author_salt: str = "local-research") -> bool:
        author_hash = hashlib.sha256(f"{author_salt}:{record.source}:{record.author_id or record.author_public_name or ''}".encode()).hexdigest() if (record.author_id or record.author_public_name) else None
        values = (
            record.source, record.source_type, record.source_id, record.canonical_url,
            record.title, record.body, record.author_public_name, author_hash,
            _dt(record.published_at), _dt(record.fetched_at), record.country_signal, record.language,
            record.score_or_votes, record.comment_count, record.rating, record.app_name,
            record.product_name, record.query, record.search_rank, record.raw_json_path,
            record.extraction_confidence, json.dumps(record.extraction_warnings),
            record.thread_id, record.parent_id, record.market_role, record.default_market,
            int(record.not_us_validation),
            text_hash(f"{record.title or ''} {record.body or ''}"), run_id,
        )
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO source_records(
               source,source_type,source_id,canonical_url,title,body,author_public_name,author_hash,
               published_at,fetched_at,country_signal,language,score_or_votes,comment_count,rating,
               app_name,product_name,query,search_rank,raw_json_path,extraction_confidence,
               extraction_warnings_json,thread_id,parent_id,market_role,default_market,
               not_us_validation,normalized_text_hash,research_run_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        row = self.conn.execute(
            "SELECT id FROM source_records WHERE source=? AND source_id=?",
            (record.source, record.source_id),
        ).fetchone()
        membership = self.conn.execute(
            """INSERT OR IGNORE INTO research_run_source_records(research_run_id,source_record_id,added_at)
               VALUES(?,?,?)""", (run_id, row["id"], now_iso()),
        )
        self._save_specialized_record(record, run_id)
        self.conn.commit()
        return membership.rowcount > 0

    def _save_specialized_record(self, record: SourceRecord, run_id: int) -> None:
        if record.source_type == "review":
            self.conn.execute(
                """INSERT OR IGNORE INTO product_reviews(
                   research_run_id,source,source_id,app_id,app_name,review_title,review_body,
                   rating,version,review_date,language,source_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, record.source, record.source_id, record.thread_id, record.app_name,
                 record.title, record.body or "", record.rating,
                 record.raw_payload.get("im:version", {}).get("label") if record.source == "app_store" else record.raw_payload.get("reviewCreatedVersion"),
                 _dt(record.published_at), record.language, record.canonical_url),
            )
            row = self.conn.execute(
                "SELECT id FROM product_reviews WHERE source=? AND source_id=?",
                (record.source, record.source_id),
            ).fetchone()
            self.conn.execute(
                """INSERT OR IGNORE INTO research_run_product_reviews(
                   research_run_id,product_review_id,added_at) VALUES(?,?,?)""",
                (run_id, row["id"], now_iso()),
            )
        elif record.source_type == "trend_point":
            try:
                value = float(record.score_or_votes if record.score_or_votes is not None else record.body)
            except (TypeError, ValueError):
                value = None
            self.conn.execute(
                """INSERT OR IGNORE INTO trend_series(
                   research_run_id,provider,query,geography,observed_at,value,series_type,source_url)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (run_id, record.source, record.query or record.title or "", "US",
                 _dt(record.published_at) or now_iso(), value, "interest", record.canonical_url),
            )
            row = self.conn.execute(
                """SELECT id FROM trend_series WHERE provider=? AND query=? AND geography=?
                   AND observed_at=? AND series_type=?""",
                (
                    record.source, record.query or record.title or "", "US",
                    _dt(record.published_at) or now_iso(), "interest",
                ),
            ).fetchone()
            if row:
                self.conn.execute(
                    """INSERT OR IGNORE INTO research_run_trend_series(
                       research_run_id,trend_series_id,added_at) VALUES(?,?,?)""",
                    (run_id, row["id"], now_iso()),
                )
        elif record.source_type in {"app", "product"} and record.title:
            raw = record.raw_payload
            price = raw.get("price")
            price_source = record.canonical_url if price not in (None, "") else None
            self.conn.execute(
                """INSERT OR IGNORE INTO competitors(
                   research_run_id,name,platform,official_url,current_price,price_currency,
                   price_type,price_checked_at,price_source_url,rating,review_count,
                   evidence_links_json,source_confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, record.title, record.source, record.canonical_url, price,
                 raw.get("currency") or ("USD" if price is not None else None),
                 (
                     "free_download" if price == 0
                     else "upfront_download" if price is not None
                     else None
                 ),
                 _dt(record.fetched_at) if price_source else None, price_source,
                 record.rating, record.comment_count,
                 json.dumps([record.canonical_url]), 0.8),
            )

    def save_finding(self, finding: EvidenceFinding, run_id: int) -> bool:
        data = finding.model_dump(mode="json")
        columns = list(data)
        data["research_run_id"] = run_id
        columns.insert(1, "research_run_id")
        vals = [data[c] for c in columns]
        for key in ("personal_experience",):
            vals[columns.index(key)] = int(bool(data[key]))
        update_columns = [
            column for column in columns
            if column not in {"finding_id", "research_run_id"}
        ]
        self.conn.execute(
            f"""INSERT INTO evidence_findings({','.join(columns)})
                VALUES({','.join('?' for _ in columns)})
                ON CONFLICT(finding_id) DO UPDATE SET
                {','.join(f'{column}=excluded.{column}' for column in update_columns)}""",
            vals,
        )
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO research_run_evidence_findings(
               research_run_id,finding_id,added_at) VALUES(?,?,?)""",
            (run_id, finding.finding_id, now_iso()),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def save_error(self, run_id: int, source: str, query: str | None, stage: str, exc: Exception) -> None:
        retryable = not any(token in type(exc).__name__.lower() for token in ("auth", "blocked"))
        self.conn.execute(
            """INSERT INTO crawl_errors_v2(research_run_id,source,query,stage,error_type,message,retryable,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (run_id, source, query, stage, type(exc).__name__, str(exc)[:1000], int(retryable), now_iso()),
        )
        self.conn.commit()

    def frame(self, table: str, run_id: int | None = None) -> pd.DataFrame:
        allowed = {
            "source_records", "evidence_findings", "research_runs", "source_queries",
            "competitors", "product_reviews", "trend_series", "opportunity_candidates",
            "crawl_errors_v2", "research_run_sources",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        if run_id is None:
            return pd.read_sql_query(f"SELECT * FROM {table}", self.conn)
        if table == "source_records":
            return pd.read_sql_query(
                """SELECT sr.* FROM source_records sr
                   JOIN research_run_source_records rr ON rr.source_record_id=sr.id
                   WHERE rr.research_run_id=?""",
                self.conn, params=(run_id,),
            )
        if table == "evidence_findings":
            return pd.read_sql_query(
                """SELECT ef.* FROM evidence_findings ef
                   JOIN research_run_evidence_findings rr ON rr.finding_id=ef.finding_id
                   WHERE rr.research_run_id=?""",
                self.conn, params=(run_id,),
            )
        if table == "product_reviews":
            return pd.read_sql_query(
                """SELECT pr.* FROM product_reviews pr
                   JOIN research_run_product_reviews rr ON rr.product_review_id=pr.id
                   WHERE rr.research_run_id=?""",
                self.conn, params=(run_id,),
            )
        if table == "trend_series":
            return pd.read_sql_query(
                """SELECT ts.* FROM trend_series ts
                   JOIN research_run_trend_series rr ON rr.trend_series_id=ts.id
                   WHERE rr.research_run_id=?""",
                self.conn, params=(run_id,),
            )
        if table == "research_runs":
            return pd.read_sql_query(
                "SELECT * FROM research_runs WHERE id=?",
                self.conn, params=(run_id,),
            )
        return pd.read_sql_query(f"SELECT * FROM {table} WHERE research_run_id=?", self.conn, params=(run_id,))


def _dt(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
