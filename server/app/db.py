from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .auto_reply import (
    DEFAULT_FULFILLMENT_REPLY_TEXT,
    DEFAULT_SLEEP_END,
    DEFAULT_SLEEP_REPLY_TEXT,
    DEFAULT_SLEEP_START,
    DEFAULT_SLEEP_TIMEZONE,
    AutoReplyConfig,
    normalize_clock_time,
    normalize_messages,
    normalize_timezone,
    now_iso,
)


@dataclass(slots=True)
class OrderRow:
    deal_id: str
    chat_id: str
    direction: str
    item_name: str
    price: str
    seller_net_amount: str
    seller_net_status: str
    seller_net_available_at: str
    buyer: str
    buyer_comment: str
    buyer_fields_json: str
    first_seen_at: str
    payment_message_id: str
    payment_created_at: str
    reply_attempted: bool
    reply_sent: bool
    reply_message_id: str
    reply_messages_json: str
    reply_mode: str
    sleep_reply_eligible: bool
    sleep_reply_attempted: bool
    sleep_reply_sent: bool
    sleep_reply_message_id: str
    sleep_reply_text: str
    wake_reply_requested: bool
    wake_reply_requested_at: str
    fulfillment_reply_eligible: bool
    fulfillment_reply_attempted: bool
    fulfillment_reply_sent: bool
    fulfillment_reply_message_id: str
    fulfillment_reply_text: str
    last_error: str
    problem_active: bool
    problem_message_id: str
    problem_resolved_message_id: str
    problem_reported_at: str
    problem_resolved_at: str
    problem_reported_by_name: str
    problem_reported_by_role: str
    problem_reported_by_relation: str
    problem_resolved_by_name: str
    problem_resolved_by_role: str
    problem_resolved_by_relation: str
    rolled_back: bool
    rolled_back_message_id: str
    rolled_back_at: str
    rolled_back_by_name: str
    rolled_back_by_role: str
    rolled_back_by_relation: str
    deal_status: str
    seller_fulfilled: bool
    seller_fulfilled_message_id: str
    seller_fulfilled_at: str
    seller_fulfilled_by_name: str
    seller_fulfilled_by_role: str
    seller_fulfilled_by_relation: str
    recipient_confirmed: bool
    recipient_confirmed_message_id: str
    recipient_confirmed_at: str
    recipient_confirmation_automatic: bool
    recipient_confirmed_by_name: str
    recipient_confirmed_by_role: str
    recipient_confirmed_by_relation: str
    review_id: str
    review_rating: int
    review_text: str
    review_created_at: str
    review_updated_at: str
    review_author: str
    review_details_loaded: bool
    relist_eligible: bool
    relist_state: str
    relist_source_item_id: str
    relist_source_item_slug: str
    relist_draft_item_id: str
    relist_draft_item_slug: str
    relist_draft_created_at: str
    relisted_item_id: str
    relisted_item_slug: str
    relist_priority_price: int
    relist_priority_type: str
    relist_listing_price: int
    relist_started_at: str
    relisted_at: str
    relist_error: str
    relist_attempts: int
    updated_at: str
    revision: int


@dataclass(slots=True)
class RelistReceipt:
    deal_id: str
    source_item_id: str
    source_item_slug: str
    published_item_id: str
    published_item_slug: str
    priority_price: int
    priority_type: str
    published_at: str


@dataclass(slots=True)
class EventRow:
    id: int
    event_key: str
    deal_id: str
    kind: str
    title: str
    body: str
    created_at: str


class OrderStore:
    def __init__(self, path: Path) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=3000")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    deal_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT '',
                    item_name TEXT NOT NULL DEFAULT '',
                    price TEXT NOT NULL DEFAULT '',
                    seller_net_amount TEXT NOT NULL DEFAULT '',
                    seller_net_status TEXT NOT NULL DEFAULT '',
                    seller_net_available_at TEXT NOT NULL DEFAULT '',
                    buyer TEXT NOT NULL DEFAULT '',
                    buyer_comment TEXT NOT NULL DEFAULT '',
                    buyer_fields_json TEXT NOT NULL DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    payment_message_id TEXT NOT NULL DEFAULT '',
                    payment_created_at TEXT NOT NULL DEFAULT '',
                    reply_attempted INTEGER NOT NULL DEFAULT 0,
                    reply_sent INTEGER NOT NULL DEFAULT 0,
                    reply_message_id TEXT NOT NULL DEFAULT '',
                    reply_messages_json TEXT NOT NULL DEFAULT '',
                    reply_mode TEXT NOT NULL DEFAULT '',
                    sleep_reply_eligible INTEGER NOT NULL DEFAULT 0,
                    sleep_reply_attempted INTEGER NOT NULL DEFAULT 0,
                    sleep_reply_sent INTEGER NOT NULL DEFAULT 0,
                    sleep_reply_message_id TEXT NOT NULL DEFAULT '',
                    sleep_reply_text TEXT NOT NULL DEFAULT '',
                    wake_reply_requested INTEGER NOT NULL DEFAULT 0,
                    wake_reply_requested_at TEXT NOT NULL DEFAULT '',
                    fulfillment_reply_eligible INTEGER NOT NULL DEFAULT 0,
                    fulfillment_reply_attempted INTEGER NOT NULL DEFAULT 0,
                    fulfillment_reply_sent INTEGER NOT NULL DEFAULT 0,
                    fulfillment_reply_message_id TEXT NOT NULL DEFAULT '',
                    fulfillment_reply_text TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    problem_active INTEGER NOT NULL DEFAULT 0,
                    problem_message_id TEXT NOT NULL DEFAULT '',
                    problem_resolved_message_id TEXT NOT NULL DEFAULT '',
                    problem_reported_at TEXT NOT NULL DEFAULT '',
                    problem_resolved_at TEXT NOT NULL DEFAULT '',
                    problem_reported_by_name TEXT NOT NULL DEFAULT '',
                    problem_reported_by_role TEXT NOT NULL DEFAULT '',
                    problem_reported_by_relation TEXT NOT NULL DEFAULT '',
                    problem_resolved_by_name TEXT NOT NULL DEFAULT '',
                    problem_resolved_by_role TEXT NOT NULL DEFAULT '',
                    problem_resolved_by_relation TEXT NOT NULL DEFAULT '',
                    rolled_back INTEGER NOT NULL DEFAULT 0,
                    rolled_back_message_id TEXT NOT NULL DEFAULT '',
                    rolled_back_at TEXT NOT NULL DEFAULT '',
                    rolled_back_by_name TEXT NOT NULL DEFAULT '',
                    rolled_back_by_role TEXT NOT NULL DEFAULT '',
                    rolled_back_by_relation TEXT NOT NULL DEFAULT '',
                    deal_status TEXT NOT NULL DEFAULT '',
                    seller_fulfilled INTEGER NOT NULL DEFAULT 0,
                    seller_fulfilled_message_id TEXT NOT NULL DEFAULT '',
                    seller_fulfilled_at TEXT NOT NULL DEFAULT '',
                    seller_fulfilled_by_name TEXT NOT NULL DEFAULT '',
                    seller_fulfilled_by_role TEXT NOT NULL DEFAULT '',
                    seller_fulfilled_by_relation TEXT NOT NULL DEFAULT '',
                    recipient_confirmed INTEGER NOT NULL DEFAULT 0,
                    recipient_confirmed_message_id TEXT NOT NULL DEFAULT '',
                    recipient_confirmed_at TEXT NOT NULL DEFAULT '',
                    recipient_confirmation_automatic INTEGER NOT NULL DEFAULT 0,
                    recipient_confirmed_by_name TEXT NOT NULL DEFAULT '',
                    recipient_confirmed_by_role TEXT NOT NULL DEFAULT '',
                    recipient_confirmed_by_relation TEXT NOT NULL DEFAULT '',
                    review_id TEXT NOT NULL DEFAULT '',
                    review_rating INTEGER NOT NULL DEFAULT 0,
                    review_text TEXT NOT NULL DEFAULT '',
                    review_created_at TEXT NOT NULL DEFAULT '',
                    review_updated_at TEXT NOT NULL DEFAULT '',
                    review_author TEXT NOT NULL DEFAULT '',
                    review_details_loaded INTEGER NOT NULL DEFAULT 0,
                    relist_eligible INTEGER NOT NULL DEFAULT 0,
                    relist_state TEXT NOT NULL DEFAULT '',
                    relist_source_item_id TEXT NOT NULL DEFAULT '',
                    relist_source_item_slug TEXT NOT NULL DEFAULT '',
                    relist_draft_item_id TEXT NOT NULL DEFAULT '',
                    relist_draft_item_slug TEXT NOT NULL DEFAULT '',
                    relist_draft_created_at TEXT NOT NULL DEFAULT '',
                    relisted_item_id TEXT NOT NULL DEFAULT '',
                    relisted_item_slug TEXT NOT NULL DEFAULT '',
                    relist_priority_price INTEGER NOT NULL DEFAULT 0,
                    relist_priority_type TEXT NOT NULL DEFAULT '',
                    relist_listing_price INTEGER NOT NULL DEFAULT 0,
                    relist_started_at TEXT NOT NULL DEFAULT '',
                    relisted_at TEXT NOT NULL DEFAULT '',
                    relist_error TEXT NOT NULL DEFAULT '',
                    relist_attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Online migration for all earlier monitor versions.
            self._ensure_column("orders", "direction", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "payment_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "payment_created_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_net_amount", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_net_status", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_net_available_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "reply_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "reply_messages_json", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "reply_mode", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                "orders", "sleep_reply_eligible", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "sleep_reply_attempted", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "sleep_reply_sent", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "sleep_reply_message_id", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                "orders", "sleep_reply_text", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                "orders", "wake_reply_requested", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "wake_reply_requested_at", "TEXT NOT NULL DEFAULT ''"
            )
            fulfillment_reply_added = self._ensure_column(
                "orders", "fulfillment_reply_eligible", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "fulfillment_reply_attempted", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "fulfillment_reply_sent", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                "orders", "fulfillment_reply_message_id", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                "orders", "fulfillment_reply_text", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column("orders", "buyer_comment", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "buyer_fields_json", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_active", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "problem_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_resolved_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_reported_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_resolved_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_reported_by_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_reported_by_role", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_reported_by_relation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_resolved_by_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_resolved_by_role", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "problem_resolved_by_relation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "rolled_back", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "rolled_back_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "rolled_back_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "rolled_back_by_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "rolled_back_by_role", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "rolled_back_by_relation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "deal_status", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_fulfilled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "seller_fulfilled_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_fulfilled_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_fulfilled_by_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_fulfilled_by_role", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "seller_fulfilled_by_relation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "recipient_confirmed", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "recipient_confirmed_message_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "recipient_confirmed_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "recipient_confirmation_automatic", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "recipient_confirmed_by_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "recipient_confirmed_by_role", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "recipient_confirmed_by_relation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "review_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "review_rating", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "review_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "review_created_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "review_updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "review_author", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "review_details_loaded", "INTEGER NOT NULL DEFAULT 0")
            # Existing rows stay ineligible. Only record() may opt in a newly
            # observed order after this migration has completed.
            self._ensure_column("orders", "relist_eligible", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "relist_state", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_source_item_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_source_item_slug", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_draft_item_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_draft_item_slug", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_draft_created_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relisted_item_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relisted_item_slug", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_priority_price", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "relist_priority_type", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_listing_price", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "relist_started_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relisted_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_error", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "relist_attempts", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("orders", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("orders", "revision", "INTEGER NOT NULL DEFAULT 0")

            # Arm only unfinished sales during the one-time migration.  Already
            # fulfilled history remains permanently ineligible, so a watcher
            # replay or service restart cannot send a catch-up message.  Current
            # open sales are armed because their future ITEM_SENT transition is
            # a new action by this account.
            if fulfillment_reply_added:
                self._conn.execute(
                    """UPDATE orders SET fulfillment_reply_eligible=1
                       WHERE direction='OUT' AND seller_fulfilled=0 AND rolled_back=0"""
                )

            # A successful relist is an immutable receipt keyed by deal_id.  The
            # primary key is the database-level guarantee that one source order
            # can never produce a second successful relist.
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relist_receipts (
                    deal_id TEXT PRIMARY KEY,
                    source_item_id TEXT NOT NULL,
                    source_item_slug TEXT NOT NULL DEFAULT '',
                    published_item_id TEXT NOT NULL,
                    published_item_slug TEXT NOT NULL DEFAULT '',
                    priority_price INTEGER NOT NULL DEFAULT 0,
                    priority_type TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL,
                    FOREIGN KEY(deal_id) REFERENCES orders(deal_id)
                )
                """
            )

            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ref_deal_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'ORDER_PAID'
                )
                """
            )
            # Keep the historical UNIQUE(deal_id) column as a generic event key.
            # Problem events use a message-scoped synthetic key, while ref_deal_id
            # always points to the real Playerok deal.
            self._ensure_column("events", "ref_deal_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("events", "kind", "TEXT NOT NULL DEFAULT 'ORDER_PAID'")
            self._conn.execute(
                "UPDATE events SET ref_deal_id=deal_id WHERE ref_deal_id=''"
            )

            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS events_id_idx ON events(id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS orders_chat_idx ON orders(chat_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS orders_direction_idx ON orders(direction)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS orders_revision_idx ON orders(revision)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS orders_problem_idx ON orders(problem_active)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS orders_rolled_back_idx ON orders(rolled_back)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS orders_relist_state_idx ON orders(relist_state)")

            # Give installations upgraded from v9 a single initial revision so the
            # Android client can perform one full sync, then use cheap revision checks.
            meta = self._conn.execute(
                "SELECT value FROM meta WHERE key='orders_revision'"
            ).fetchone()
            if meta is None:
                count = int(self._conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
                initial = 1 if count else 0
                self._conn.execute(
                    "INSERT INTO meta(key,value) VALUES('orders_revision',?)",
                    (str(initial),),
                )
                if count:
                    self._conn.execute(
                        """UPDATE orders
                           SET revision=CASE WHEN revision=0 THEN ? ELSE revision END,
                               updated_at=CASE WHEN updated_at='' THEN first_seen_at ELSE updated_at END""",
                        (initial,),
                    )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _ensure_column(self, table: str, column: str, declaration: str) -> bool:
        columns = {
            str(row["name"])
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
            return True
        return False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _next_revision_locked(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='orders_revision'"
        ).fetchone()
        current = int(row[0]) if row is not None else 0
        new_value = current + 1
        self._conn.execute(
            "INSERT INTO meta(key,value) VALUES('orders_revision',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(new_value),),
        )
        return new_value

    def current_revision(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key='orders_revision'"
            ).fetchone()
            return int(row[0]) if row is not None else 0

    @staticmethod
    def _order(row: sqlite3.Row | None) -> OrderRow | None:
        if row is None:
            return None
        keys = set(row.keys())
        return OrderRow(
            deal_id=row["deal_id"],
            chat_id=row["chat_id"],
            direction=(row["direction"] if "direction" in keys else ""),
            item_name=row["item_name"],
            price=row["price"],
            seller_net_amount=row["seller_net_amount"] if "seller_net_amount" in keys else "",
            seller_net_status=row["seller_net_status"] if "seller_net_status" in keys else "",
            seller_net_available_at=row["seller_net_available_at"] if "seller_net_available_at" in keys else "",
            buyer=row["buyer"],
            buyer_comment=row["buyer_comment"] if "buyer_comment" in keys else "",
            buyer_fields_json=(
                row["buyer_fields_json"] if "buyer_fields_json" in keys else ""
            ),
            first_seen_at=row["first_seen_at"],
            payment_message_id=row["payment_message_id"] if "payment_message_id" in keys else "",
            payment_created_at=row["payment_created_at"] if "payment_created_at" in keys else "",
            reply_attempted=bool(row["reply_attempted"]),
            reply_sent=bool(row["reply_sent"]),
            reply_message_id=row["reply_message_id"] if "reply_message_id" in keys else "",
            reply_messages_json=row["reply_messages_json"] if "reply_messages_json" in keys else "",
            reply_mode=row["reply_mode"] if "reply_mode" in keys else "",
            sleep_reply_eligible=(
                bool(row["sleep_reply_eligible"])
                if "sleep_reply_eligible" in keys else False
            ),
            sleep_reply_attempted=(
                bool(row["sleep_reply_attempted"])
                if "sleep_reply_attempted" in keys else False
            ),
            sleep_reply_sent=(
                bool(row["sleep_reply_sent"])
                if "sleep_reply_sent" in keys else False
            ),
            sleep_reply_message_id=(
                row["sleep_reply_message_id"]
                if "sleep_reply_message_id" in keys else ""
            ),
            sleep_reply_text=(
                row["sleep_reply_text"] if "sleep_reply_text" in keys else ""
            ),
            wake_reply_requested=(
                bool(row["wake_reply_requested"])
                if "wake_reply_requested" in keys else False
            ),
            wake_reply_requested_at=(
                row["wake_reply_requested_at"]
                if "wake_reply_requested_at" in keys else ""
            ),
            fulfillment_reply_eligible=(
                bool(row["fulfillment_reply_eligible"])
                if "fulfillment_reply_eligible" in keys else False
            ),
            fulfillment_reply_attempted=(
                bool(row["fulfillment_reply_attempted"])
                if "fulfillment_reply_attempted" in keys else False
            ),
            fulfillment_reply_sent=(
                bool(row["fulfillment_reply_sent"])
                if "fulfillment_reply_sent" in keys else False
            ),
            fulfillment_reply_message_id=(
                row["fulfillment_reply_message_id"]
                if "fulfillment_reply_message_id" in keys else ""
            ),
            fulfillment_reply_text=(
                row["fulfillment_reply_text"]
                if "fulfillment_reply_text" in keys else ""
            ),
            last_error=row["last_error"],
            problem_active=bool(row["problem_active"]) if "problem_active" in keys else False,
            problem_message_id=row["problem_message_id"] if "problem_message_id" in keys else "",
            problem_resolved_message_id=row["problem_resolved_message_id"] if "problem_resolved_message_id" in keys else "",
            problem_reported_at=row["problem_reported_at"] if "problem_reported_at" in keys else "",
            problem_resolved_at=row["problem_resolved_at"] if "problem_resolved_at" in keys else "",
            problem_reported_by_name=row["problem_reported_by_name"] if "problem_reported_by_name" in keys else "",
            problem_reported_by_role=row["problem_reported_by_role"] if "problem_reported_by_role" in keys else "",
            problem_reported_by_relation=row["problem_reported_by_relation"] if "problem_reported_by_relation" in keys else "",
            problem_resolved_by_name=row["problem_resolved_by_name"] if "problem_resolved_by_name" in keys else "",
            problem_resolved_by_role=row["problem_resolved_by_role"] if "problem_resolved_by_role" in keys else "",
            problem_resolved_by_relation=row["problem_resolved_by_relation"] if "problem_resolved_by_relation" in keys else "",
            rolled_back=bool(row["rolled_back"]) if "rolled_back" in keys else False,
            rolled_back_message_id=row["rolled_back_message_id"] if "rolled_back_message_id" in keys else "",
            rolled_back_at=row["rolled_back_at"] if "rolled_back_at" in keys else "",
            rolled_back_by_name=row["rolled_back_by_name"] if "rolled_back_by_name" in keys else "",
            rolled_back_by_role=row["rolled_back_by_role"] if "rolled_back_by_role" in keys else "",
            rolled_back_by_relation=row["rolled_back_by_relation"] if "rolled_back_by_relation" in keys else "",
            deal_status=row["deal_status"] if "deal_status" in keys else "",
            seller_fulfilled=bool(row["seller_fulfilled"]) if "seller_fulfilled" in keys else False,
            seller_fulfilled_message_id=row["seller_fulfilled_message_id"] if "seller_fulfilled_message_id" in keys else "",
            seller_fulfilled_at=row["seller_fulfilled_at"] if "seller_fulfilled_at" in keys else "",
            seller_fulfilled_by_name=row["seller_fulfilled_by_name"] if "seller_fulfilled_by_name" in keys else "",
            seller_fulfilled_by_role=row["seller_fulfilled_by_role"] if "seller_fulfilled_by_role" in keys else "",
            seller_fulfilled_by_relation=row["seller_fulfilled_by_relation"] if "seller_fulfilled_by_relation" in keys else "",
            recipient_confirmed=bool(row["recipient_confirmed"]) if "recipient_confirmed" in keys else False,
            recipient_confirmed_message_id=row["recipient_confirmed_message_id"] if "recipient_confirmed_message_id" in keys else "",
            recipient_confirmed_at=row["recipient_confirmed_at"] if "recipient_confirmed_at" in keys else "",
            recipient_confirmation_automatic=bool(row["recipient_confirmation_automatic"]) if "recipient_confirmation_automatic" in keys else False,
            recipient_confirmed_by_name=row["recipient_confirmed_by_name"] if "recipient_confirmed_by_name" in keys else "",
            recipient_confirmed_by_role=row["recipient_confirmed_by_role"] if "recipient_confirmed_by_role" in keys else "",
            recipient_confirmed_by_relation=row["recipient_confirmed_by_relation"] if "recipient_confirmed_by_relation" in keys else "",
            review_id=row["review_id"] if "review_id" in keys else "",
            review_rating=int(row["review_rating"]) if "review_rating" in keys else 0,
            review_text=row["review_text"] if "review_text" in keys else "",
            review_created_at=row["review_created_at"] if "review_created_at" in keys else "",
            review_updated_at=row["review_updated_at"] if "review_updated_at" in keys else "",
            review_author=row["review_author"] if "review_author" in keys else "",
            review_details_loaded=bool(row["review_details_loaded"]) if "review_details_loaded" in keys else False,
            relist_eligible=bool(row["relist_eligible"]) if "relist_eligible" in keys else False,
            relist_state=row["relist_state"] if "relist_state" in keys else "",
            relist_source_item_id=row["relist_source_item_id"] if "relist_source_item_id" in keys else "",
            relist_source_item_slug=row["relist_source_item_slug"] if "relist_source_item_slug" in keys else "",
            relist_draft_item_id=row["relist_draft_item_id"] if "relist_draft_item_id" in keys else "",
            relist_draft_item_slug=row["relist_draft_item_slug"] if "relist_draft_item_slug" in keys else "",
            relist_draft_created_at=row["relist_draft_created_at"] if "relist_draft_created_at" in keys else "",
            relisted_item_id=row["relisted_item_id"] if "relisted_item_id" in keys else "",
            relisted_item_slug=row["relisted_item_slug"] if "relisted_item_slug" in keys else "",
            relist_priority_price=int(row["relist_priority_price"]) if "relist_priority_price" in keys else 0,
            relist_priority_type=row["relist_priority_type"] if "relist_priority_type" in keys else "",
            relist_listing_price=int(row["relist_listing_price"]) if "relist_listing_price" in keys else 0,
            relist_started_at=row["relist_started_at"] if "relist_started_at" in keys else "",
            relisted_at=row["relisted_at"] if "relisted_at" in keys else "",
            relist_error=row["relist_error"] if "relist_error" in keys else "",
            relist_attempts=int(row["relist_attempts"]) if "relist_attempts" in keys else 0,
            updated_at=row["updated_at"] if "updated_at" in keys else row["first_seen_at"],
            revision=int(row["revision"]) if "revision" in keys else 0,
        )

    @staticmethod
    def _event(row: sqlite3.Row | None) -> EventRow | None:
        if row is None:
            return None
        keys = set(row.keys())
        event_key = row["deal_id"]
        ref = row["ref_deal_id"] if "ref_deal_id" in keys else ""
        return EventRow(
            id=int(row["id"]),
            event_key=event_key,
            deal_id=ref or event_key,
            kind=(row["kind"] if "kind" in keys else "ORDER_PAID") or "ORDER_PAID",
            title=row["title"],
            body=row["body"],
            created_at=row["created_at"],
        )

    def record(
        self,
        deal_id: str,
        chat_id: str,
        item_name: str,
        price: str,
        buyer: str,
        payment_message_id: str = "",
        payment_created_at: str = "",
        buyer_comment: str = "",
        buyer_fields_json: str = "",
        direction: str = "",
        seller_net_amount: str = "",
        seller_net_status: str = "",
        seller_net_available_at: str = "",
    ) -> OrderRow:
        direction = (direction or "").strip().upper()
        if direction not in {"IN", "OUT"}:
            direction = ""
        if direction == "IN":
            seller_net_amount = ""
            seller_net_status = ""
            seller_net_available_at = ""
        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM orders WHERE deal_id=?", (deal_id,)
            ).fetchone()
            now = self._now()
            if existing is None:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """INSERT INTO orders
                       (deal_id,chat_id,direction,item_name,price,seller_net_amount,seller_net_status,
                        seller_net_available_at,buyer,buyer_comment,buyer_fields_json,first_seen_at,
                        payment_message_id,payment_created_at,sleep_reply_eligible,
                        fulfillment_reply_eligible,relist_eligible,updated_at,revision)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        deal_id,
                        chat_id,
                        direction,
                        item_name,
                        price,
                        seller_net_amount,
                        seller_net_status,
                        seller_net_available_at,
                        buyer,
                        buyer_comment,
                        buyer_fields_json,
                        now,
                        payment_message_id,
                        payment_created_at,
                        1,
                        1,
                        1,
                        now,
                        rev,
                    ),
                )
            else:
                old = self._order(existing)
                assert old is not None
                values = {
                    "chat_id": old.chat_id or chat_id,
                    "direction": old.direction if old.direction in {"IN", "OUT"} else direction,
                    "item_name": old.item_name or item_name,
                    "price": old.price or price,
                    "seller_net_amount": seller_net_amount or old.seller_net_amount,
                    "seller_net_status": seller_net_status or old.seller_net_status,
                    "seller_net_available_at": (
                        seller_net_available_at
                        if seller_net_status
                        else old.seller_net_available_at
                    ),
                    "buyer": old.buyer or buyer,
                    "buyer_comment": old.buyer_comment or buyer_comment,
                    "buyer_fields_json": buyer_fields_json or old.buyer_fields_json,
                    "payment_message_id": old.payment_message_id or payment_message_id,
                    "payment_created_at": old.payment_created_at or payment_created_at,
                }
                changed = any(
                    getattr(old, key) != value for key, value in values.items()
                )
                if changed:
                    rev = self._next_revision_locked()
                    self._conn.execute(
                        """UPDATE orders SET
                           chat_id=?, direction=?, item_name=?, price=?, seller_net_amount=?,
                           seller_net_status=?, seller_net_available_at=?, buyer=?, buyer_comment=?,
                           buyer_fields_json=?,
                           payment_message_id=?, payment_created_at=?, updated_at=?, revision=?
                           WHERE deal_id=?""",
                        (
                            values["chat_id"],
                            values["direction"],
                            values["item_name"],
                            values["price"],
                            values["seller_net_amount"],
                            values["seller_net_status"],
                            values["seller_net_available_at"],
                            values["buyer"],
                            values["buyer_comment"],
                            values["buyer_fields_json"],
                            values["payment_message_id"],
                            values["payment_created_at"],
                            now,
                            rev,
                            deal_id,
                        ),
                    )
            self._conn.commit()
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            assert row is not None
            return row

    def get(self, deal_id: str) -> OrderRow | None:
        with self._lock:
            return self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )

    def list_orders(self, limit: int = 100) -> list[OrderRow]:
        safe_limit = max(1, min(200, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   ORDER BY COALESCE(NULLIF(payment_created_at,''), first_seen_at) DESC, deal_id DESC
                   LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def list_orders_needing_direction(self, limit: int = 500) -> list[OrderRow]:
        safe_limit = max(1, min(1000, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM orders WHERE direction NOT IN ('IN','OUT') ORDER BY first_seen_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def list_orders_needing_buyer_fields(self, limit: int = 100) -> list[OrderRow]:
        safe_limit = max(1, min(200, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   WHERE buyer_fields_json=''
                   ORDER BY first_seen_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def set_buyer_fields(
        self,
        deal_id: str,
        fields_json: str,
    ) -> tuple[OrderRow | None, bool]:
        clean = (fields_json or "").strip()
        if not clean:
            return self.get(deal_id), False
        with self._lock:
            row = self._order(
                self._conn.execute(
                    "SELECT * FROM orders WHERE deal_id=?", (deal_id,)
                ).fetchone()
            )
            if row is None or row.buyer_fields_json == clean:
                return row, False
            now = self._now()
            revision = self._next_revision_locked()
            self._conn.execute(
                """UPDATE orders
                   SET buyer_fields_json=?, updated_at=?, revision=?
                   WHERE deal_id=?""",
                (clean, now, revision, deal_id),
            )
            self._conn.commit()
            updated = self._order(
                self._conn.execute(
                    "SELECT * FROM orders WHERE deal_id=?", (deal_id,)
                ).fetchone()
            )
            return updated, True

    def list_orders_needing_financials(self, limit: int = 100) -> list[OrderRow]:
        safe_limit = max(1, min(200, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   WHERE direction='OUT' AND seller_net_amount=''
                   ORDER BY first_seen_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def list_orders_with_pending_financials(self, limit: int = 50) -> list[OrderRow]:
        safe_limit = max(1, min(100, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   WHERE direction='OUT' AND seller_net_status IN ('PENDING','PROCESSING')
                   ORDER BY first_seen_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def set_seller_financials(
        self,
        deal_id: str,
        *,
        amount: str,
        status: str,
        available_at: str = "",
    ) -> tuple[OrderRow | None, bool]:
        clean_amount = (amount or "").strip()
        clean_status = (status or "").strip().upper()
        clean_available_at = (available_at or "").strip()
        if not clean_amount and not clean_status:
            return self.get(deal_id), False
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None or row.direction != "OUT":
                return row, False
            values = (
                clean_amount or row.seller_net_amount,
                clean_status or row.seller_net_status,
                clean_available_at if clean_status else row.seller_net_available_at,
            )
            current = (
                row.seller_net_amount,
                row.seller_net_status,
                row.seller_net_available_at,
            )
            if values == current:
                return row, False
            rev = self._next_revision_locked()
            self._conn.execute(
                """UPDATE orders SET seller_net_amount=?, seller_net_status=?,
                   seller_net_available_at=?, updated_at=?, revision=? WHERE deal_id=?""",
                (*values, self._now(), rev, deal_id),
            )
            self._conn.commit()
            updated = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            return updated, True

    def set_direction(self, deal_id: str, direction: str) -> OrderRow | None:
        normalized = (direction or "").strip().upper()
        if normalized not in {"IN", "OUT"}:
            return self.get(deal_id)
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return None
            if row.direction != normalized:
                rev = self._next_revision_locked()
                self._conn.execute(
                    "UPDATE orders SET direction=?, updated_at=?, revision=? WHERE deal_id=?",
                    (normalized, self._now(), rev, deal_id),
                )
                self._conn.commit()
            return self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )

    def pending_replies(self, limit: int = 50) -> list[OrderRow]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   WHERE reply_attempted=1 AND reply_sent=0 AND direction='OUT'
                   ORDER BY first_seen_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def pending_sleep_replies(self, limit: int = 50) -> list[OrderRow]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   WHERE reply_mode='SLEEP'
                      AND sleep_reply_eligible=1 AND sleep_reply_sent=0
                      AND reply_sent=0 AND direction='OUT'
                   ORDER BY first_seen_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def pending_fulfillment_replies(self, limit: int = 50) -> list[OrderRow]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM orders
                   WHERE fulfillment_reply_eligible=1
                     AND fulfillment_reply_attempted=1
                     AND fulfillment_reply_sent=0
                     AND direction='OUT' AND seller_fulfilled=1 AND rolled_back=0
                   ORDER BY seller_fulfilled_at ASC, first_seen_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [x for r in rows if (x := self._order(r)) is not None]

    def get_auto_reply_config(
        self,
        default_enabled: bool,
        default_messages: list[str] | tuple[str, ...],
        default_fulfillment_message: str = DEFAULT_FULFILLMENT_REPLY_TEXT,
        default_sleep_message: str = DEFAULT_SLEEP_REPLY_TEXT,
    ) -> AutoReplyConfig:
        fallback = normalize_messages(default_messages)
        fulfillment_fallback = normalize_messages(
            [], default_fulfillment_message
        )[0]
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key='auto_reply_config'"
            ).fetchone()
        if row is None:
            return AutoReplyConfig(
                bool(default_enabled),
                fallback,
                fulfillment_message=fulfillment_fallback,
                sleep_message=default_sleep_message,
            )
        try:
            payload = json.loads(str(row[0]))
            enabled = payload.get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be boolean")
            messages = normalize_messages(payload.get("messages"), fallback[0])
            fulfillment_message = normalize_messages(
                [payload.get("fulfillment_message", fulfillment_fallback)],
                fulfillment_fallback,
            )[0]
            sleep_enabled = payload.get("sleep_enabled", False)
            if not isinstance(sleep_enabled, bool):
                raise ValueError("sleep_enabled must be boolean")
            sleep_start = normalize_clock_time(
                payload.get("sleep_start"), DEFAULT_SLEEP_START
            )
            sleep_end = normalize_clock_time(
                payload.get("sleep_end"), DEFAULT_SLEEP_END
            )
            if sleep_enabled and sleep_start == sleep_end:
                raise ValueError("sleep interval cannot have equal endpoints")
            sleep_timezone = normalize_timezone(payload.get("sleep_timezone"))
            sleep_message = normalize_messages(
                [payload.get("sleep_message", default_sleep_message)],
                default_sleep_message,
            )[0]
            return AutoReplyConfig(
                enabled,
                messages,
                max(0, int(payload.get("revision", 0))),
                str(payload.get("updated_at", "") or ""),
                fulfillment_message,
                sleep_enabled,
                sleep_start,
                sleep_end,
                sleep_timezone,
                sleep_message,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return AutoReplyConfig(
                bool(default_enabled),
                fallback,
                fulfillment_message=fulfillment_fallback,
                sleep_message=default_sleep_message,
            )

    def set_auto_reply_config(
        self,
        *,
        enabled: bool,
        messages: list[str] | tuple[str, ...],
        fallback: str,
        fulfillment_message: str = "",
        fulfillment_fallback: str = DEFAULT_FULFILLMENT_REPLY_TEXT,
        sleep_enabled: bool = False,
        sleep_start: str = DEFAULT_SLEEP_START,
        sleep_end: str = DEFAULT_SLEEP_END,
        sleep_timezone: str = DEFAULT_SLEEP_TIMEZONE,
        sleep_message: str = "",
        sleep_fallback: str = DEFAULT_SLEEP_REPLY_TEXT,
    ) -> AutoReplyConfig:
        normalized = normalize_messages(messages, fallback)
        normalized_fulfillment = normalize_messages(
            [fulfillment_message], fulfillment_fallback
        )[0]
        normalized_sleep_start = normalize_clock_time(sleep_start, DEFAULT_SLEEP_START)
        normalized_sleep_end = normalize_clock_time(sleep_end, DEFAULT_SLEEP_END)
        if sleep_enabled and normalized_sleep_start == normalized_sleep_end:
            raise ValueError("Начало и конец периода сна должны отличаться")
        normalized_sleep_timezone = normalize_timezone(sleep_timezone)
        normalized_sleep_message = normalize_messages(
            [sleep_message], sleep_fallback
        )[0]
        with self._lock:
            current_row = self._conn.execute(
                "SELECT value FROM meta WHERE key='auto_reply_config'"
            ).fetchone()
            revision = 1
            if current_row is not None:
                try:
                    revision = max(0, int(json.loads(str(current_row[0])).get("revision", 0))) + 1
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            config = AutoReplyConfig(
                bool(enabled),
                normalized,
                revision,
                now_iso(),
                normalized_fulfillment,
                bool(sleep_enabled),
                normalized_sleep_start,
                normalized_sleep_end,
                normalized_sleep_timezone,
                normalized_sleep_message,
            )
            value = json.dumps(
                {
                    "enabled": config.enabled,
                    "messages": list(config.messages),
                    "fulfillment_message": config.fulfillment_message,
                    "sleep_enabled": config.sleep_enabled,
                    "sleep_start": config.sleep_start,
                    "sleep_end": config.sleep_end,
                    "sleep_timezone": config.sleep_timezone,
                    "sleep_message": config.sleep_message,
                    "revision": config.revision,
                    "updated_at": config.updated_at,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES('auto_reply_config',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (value,),
            )
            self._conn.commit()
            return config

    def set_reply_mode_if_empty(self, deal_id: str, mode: str) -> OrderRow | None:
        normalized = (mode or "").strip().upper()
        if normalized not in {"NORMAL", "SLEEP"}:
            raise ValueError("unsupported reply mode")
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None or row.reply_mode or not row.sleep_reply_eligible:
                return row
            rev = self._next_revision_locked()
            self._conn.execute(
                """UPDATE orders SET reply_mode=?, updated_at=?, revision=?
                   WHERE deal_id=? AND reply_mode='' AND sleep_reply_eligible=1""",
                (normalized, self._now(), rev, deal_id),
            )
            self._conn.commit()
            return self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )

    def set_sleep_reply_attempted(self, deal_id: str, message: str) -> None:
        snapshot = (message or "").strip()
        with self._lock:
            self._conn.execute(
                """UPDATE orders SET sleep_reply_attempted=1,
                   sleep_reply_text=CASE
                       WHEN sleep_reply_text='' AND ?<>'' THEN ?
                       ELSE sleep_reply_text END
                   WHERE deal_id=? AND reply_mode='SLEEP' AND sleep_reply_eligible=1""",
                (snapshot, snapshot, deal_id),
            )
            self._conn.commit()

    def set_sleep_reply_sent(
        self,
        deal_id: str,
        reply_message_id: str = "",
    ) -> None:
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return
            changed = (not row.sleep_reply_sent) or (
                bool(reply_message_id) and row.sleep_reply_message_id != reply_message_id
            )
            if changed:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET sleep_reply_sent=1,
                       sleep_reply_message_id=CASE
                           WHEN ?<>'' THEN ? ELSE sleep_reply_message_id END,
                       last_error='', updated_at=?, revision=? WHERE deal_id=?""",
                    (reply_message_id, reply_message_id, self._now(), rev, deal_id),
                )
            else:
                self._conn.execute("UPDATE orders SET last_error='' WHERE deal_id=?", (deal_id,))
            self._conn.commit()

    def set_wake_reply_requested(self, deal_id: str) -> OrderRow | None:
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None or row.wake_reply_requested:
                return row
            rev = self._next_revision_locked()
            now = self._now()
            self._conn.execute(
                """UPDATE orders SET wake_reply_requested=1,
                   wake_reply_requested_at=?, updated_at=?, revision=? WHERE deal_id=?""",
                (now, now, rev, deal_id),
            )
            self._conn.commit()
            return self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )

    def set_reply_attempted(
        self,
        deal_id: str,
        messages: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        snapshot = ""
        if messages is not None:
            snapshot = json.dumps(list(messages), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._conn.execute(
                """UPDATE orders SET reply_attempted=1,
                   reply_messages_json=CASE
                       WHEN reply_messages_json='' AND ?<>'' THEN ?
                       ELSE reply_messages_json END
                   WHERE deal_id=?""",
                (snapshot, snapshot, deal_id),
            )
            self._conn.commit()

    def set_reply_sent(self, deal_id: str, reply_message_id: str = "") -> None:
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return
            changed = (not row.reply_sent) or (
                bool(reply_message_id) and row.reply_message_id != reply_message_id
            )
            if changed:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET reply_sent=1,
                       reply_message_id=CASE WHEN ?<>'' THEN ? ELSE reply_message_id END,
                       last_error='', updated_at=?, revision=? WHERE deal_id=?""",
                    (reply_message_id, reply_message_id, self._now(), rev, deal_id),
                )
            else:
                self._conn.execute("UPDATE orders SET last_error='' WHERE deal_id=?", (deal_id,))
            self._conn.commit()

    def set_fulfillment_reply_attempted(self, deal_id: str, message: str) -> None:
        snapshot = (message or "").strip()
        with self._lock:
            self._conn.execute(
                """UPDATE orders SET fulfillment_reply_attempted=1,
                   fulfillment_reply_text=CASE
                       WHEN fulfillment_reply_text='' AND ?<>'' THEN ?
                       ELSE fulfillment_reply_text END
                   WHERE deal_id=? AND fulfillment_reply_eligible=1""",
                (snapshot, snapshot, deal_id),
            )
            self._conn.commit()

    def set_fulfillment_reply_sent(
        self,
        deal_id: str,
        reply_message_id: str = "",
    ) -> None:
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return
            changed = (not row.fulfillment_reply_sent) or (
                bool(reply_message_id)
                and row.fulfillment_reply_message_id != reply_message_id
            )
            if changed:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET fulfillment_reply_sent=1,
                       fulfillment_reply_message_id=CASE
                           WHEN ?<>'' THEN ? ELSE fulfillment_reply_message_id END,
                       last_error='', updated_at=?, revision=? WHERE deal_id=?""",
                    (reply_message_id, reply_message_id, self._now(), rev, deal_id),
                )
            else:
                self._conn.execute("UPDATE orders SET last_error='' WHERE deal_id=?", (deal_id,))
            self._conn.commit()

    def _flag(self, deal_id: str, col: str) -> None:
        if col not in {"reply_attempted", "reply_sent"}:
            raise ValueError(col)
        with self._lock:
            self._conn.execute(f"UPDATE orders SET {col}=1 WHERE deal_id=?", (deal_id,))
            self._conn.commit()

    def set_error(self, deal_id: str, message: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE orders SET last_error=? WHERE deal_id=?",
                (message[:1000], deal_id),
            )
            self._conn.commit()

    def clear_error(self, deal_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE orders SET last_error='' WHERE deal_id=?", (deal_id,))
            self._conn.commit()

    def set_problem(
        self,
        deal_id: str,
        *,
        active: bool,
        message_id: str = "",
        event_at: str = "",
        actor_name: str = "",
        actor_role: str = "",
        actor_relation: str = "",
    ) -> tuple[OrderRow | None, bool]:
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return None, False

            when = event_at or self._now()
            if active:
                same_message = bool(message_id) and row.problem_message_id == message_id
                changed = (not same_message) if message_id else (not row.problem_active)
                if changed:
                    rev = self._next_revision_locked()
                    self._conn.execute(
                        """UPDATE orders SET problem_active=1,
                           problem_message_id=CASE WHEN ?<>'' THEN ? ELSE problem_message_id END,
                           problem_resolved_message_id='', problem_reported_at=?, problem_resolved_at='',
                           problem_reported_by_name=?, problem_reported_by_role=?, problem_reported_by_relation=?,
                           problem_resolved_by_name='', problem_resolved_by_role='', problem_resolved_by_relation='',
                           updated_at=?, revision=?
                           WHERE deal_id=?""",
                        (
                            message_id, message_id, when,
                            actor_name, actor_role, actor_relation,
                            self._now(), rev, deal_id,
                        ),
                    )
                elif actor_relation and not row.problem_reported_by_relation:
                    changed = True
                    rev = self._next_revision_locked()
                    self._conn.execute(
                        """UPDATE orders SET problem_reported_by_name=?,
                           problem_reported_by_role=?, problem_reported_by_relation=?,
                           updated_at=?, revision=? WHERE deal_id=?""",
                        (actor_name, actor_role, actor_relation, self._now(), rev, deal_id),
                    )
            else:
                same_message = bool(message_id) and row.problem_resolved_message_id == message_id
                changed = (not same_message) if message_id else row.problem_active
                if changed:
                    rev = self._next_revision_locked()
                    self._conn.execute(
                        """UPDATE orders SET problem_active=0,
                           problem_resolved_message_id=CASE WHEN ?<>'' THEN ? ELSE problem_resolved_message_id END,
                           problem_resolved_at=?,
                           problem_resolved_by_name=?, problem_resolved_by_role=?, problem_resolved_by_relation=?,
                           updated_at=?, revision=?
                           WHERE deal_id=?""",
                        (
                            message_id, message_id, when, actor_name, actor_role, actor_relation,
                            self._now(), rev, deal_id,
                        ),
                    )
                elif actor_relation and not row.problem_resolved_by_relation:
                    changed = True
                    rev = self._next_revision_locked()
                    self._conn.execute(
                        """UPDATE orders SET problem_resolved_by_name=?,
                           problem_resolved_by_role=?, problem_resolved_by_relation=?,
                           updated_at=?, revision=? WHERE deal_id=?""",
                        (actor_name, actor_role, actor_relation, self._now(), rev, deal_id),
                    )
            self._conn.commit()
            updated = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            return updated, changed

    def set_rolled_back(
        self,
        deal_id: str,
        *,
        message_id: str = "",
        event_at: str = "",
        actor_name: str = "",
        actor_role: str = "",
        actor_relation: str = "",
    ) -> tuple[OrderRow | None, bool]:
        """Persist Playerok's {{DEAL_ROLLED_BACK}} marker idempotently."""
        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return None, False

            changed = (not row.rolled_back) or (
                bool(message_id) and row.rolled_back_message_id != message_id
            )
            if changed:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET rolled_back=1,
                       rolled_back_message_id=CASE WHEN ?<>'' THEN ? ELSE rolled_back_message_id END,
                       rolled_back_at=?, rolled_back_by_name=?, rolled_back_by_role=?,
                       rolled_back_by_relation=?, updated_at=?, revision=?
                       WHERE deal_id=?""",
                    (
                        message_id, message_id, event_at or self._now(),
                        actor_name, actor_role, actor_relation,
                        self._now(), rev, deal_id,
                    ),
                )
            self._conn.commit()
            updated = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            return updated, changed

    def set_deal_progress(
        self,
        deal_id: str,
        *,
        deal_status: str = "",
        seller_fulfilled: bool = False,
        seller_message_id: str = "",
        seller_at: str = "",
        recipient_confirmed: bool = False,
        recipient_message_id: str = "",
        recipient_at: str = "",
        recipient_automatic: bool = False,
        actor_name: str = "",
        actor_role: str = "",
        actor_relation: str = "",
    ) -> tuple[OrderRow | None, bool]:
        """Persist fulfillment/receipt markers monotonically and idempotently."""
        ranks = {
            "": 0,
            "PAID": 1,
            "PENDING": 2,
            "SENT": 3,
            "CONFIRMED": 4,
            "CONFIRMED_AUTOMATICALLY": 4,
            "ROLLED_BACK": 5,
        }
        normalized = (deal_status or "").strip().upper().rsplit(".", 1)[-1]
        if normalized not in ranks:
            normalized = ""

        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return None, False

            status = row.deal_status
            if ranks.get(normalized, 0) > ranks.get(status, 0):
                status = normalized

            seller_now = row.seller_fulfilled or seller_fulfilled
            recipient_now = row.recipient_confirmed or recipient_confirmed
            automatic_now = row.recipient_confirmation_automatic or recipient_automatic
            seller_id = row.seller_fulfilled_message_id or seller_message_id
            seller_when = row.seller_fulfilled_at or (seller_at if seller_fulfilled else "")
            recipient_id = row.recipient_confirmed_message_id or recipient_message_id
            recipient_when = row.recipient_confirmed_at or (recipient_at if recipient_confirmed else "")

            seller_name = row.seller_fulfilled_by_name
            seller_role = row.seller_fulfilled_by_role
            seller_relation = row.seller_fulfilled_by_relation
            if seller_fulfilled and not seller_relation:
                seller_name, seller_role, seller_relation = actor_name, actor_role, actor_relation

            recipient_name = row.recipient_confirmed_by_name
            recipient_role = row.recipient_confirmed_by_role
            recipient_relation = row.recipient_confirmed_by_relation
            if recipient_confirmed and not recipient_relation:
                recipient_name, recipient_role, recipient_relation = actor_name, actor_role, actor_relation

            changed = any((
                status != row.deal_status,
                seller_now != row.seller_fulfilled,
                seller_id != row.seller_fulfilled_message_id,
                seller_when != row.seller_fulfilled_at,
                seller_relation != row.seller_fulfilled_by_relation,
                recipient_now != row.recipient_confirmed,
                recipient_id != row.recipient_confirmed_message_id,
                recipient_when != row.recipient_confirmed_at,
                automatic_now != row.recipient_confirmation_automatic,
                recipient_relation != row.recipient_confirmed_by_relation,
            ))
            if changed:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET deal_status=?,
                       seller_fulfilled=?, seller_fulfilled_message_id=?, seller_fulfilled_at=?,
                       seller_fulfilled_by_name=?, seller_fulfilled_by_role=?, seller_fulfilled_by_relation=?,
                       recipient_confirmed=?, recipient_confirmed_message_id=?, recipient_confirmed_at=?,
                       recipient_confirmation_automatic=?, recipient_confirmed_by_name=?,
                       recipient_confirmed_by_role=?, recipient_confirmed_by_relation=?,
                       updated_at=?, revision=? WHERE deal_id=?""",
                    (
                        status,
                        int(seller_now), seller_id, seller_when,
                        seller_name, seller_role, seller_relation,
                        int(recipient_now), recipient_id, recipient_when,
                        int(automatic_now), recipient_name, recipient_role, recipient_relation,
                        self._now(), rev, deal_id,
                    ),
                )
                self._conn.commit()
            updated = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            return updated, changed

    def set_review(
        self,
        deal_id: str,
        *,
        review_id: str = "",
        rating: int = 0,
        text: str = "",
        created_at: str = "",
        updated_at: str = "",
        author: str = "",
        details_loaded: bool = False,
    ) -> tuple[OrderRow | None, bool]:
        """Persist a Playerok testimonial without losing already loaded details.

        The paginated deals query currently contains only testimonial id/rating,
        while the individual deal query contains text and timestamps.  A partial
        refresh may therefore enrich the identity/rating but must never erase a
        previously fetched comment.
        """
        review_id = (review_id or "").strip()
        try:
            rating = max(0, min(5, int(rating or 0)))
        except (TypeError, ValueError):
            rating = 0
        if not review_id and rating <= 0:
            return self.get(deal_id), False

        with self._lock:
            row = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            if row is None:
                return None, False

            next_id = review_id or row.review_id
            next_rating = rating or row.review_rating
            next_text = text if details_loaded else row.review_text
            next_created = created_at if details_loaded else row.review_created_at
            next_updated = updated_at if details_loaded else row.review_updated_at
            next_author = author if details_loaded else row.review_author
            next_loaded = row.review_details_loaded or details_loaded
            changed = any((
                next_id != row.review_id,
                next_rating != row.review_rating,
                next_text != row.review_text,
                next_created != row.review_created_at,
                next_updated != row.review_updated_at,
                next_author != row.review_author,
                next_loaded != row.review_details_loaded,
            ))
            if changed:
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET review_id=?, review_rating=?, review_text=?,
                       review_created_at=?, review_updated_at=?, review_author=?,
                       review_details_loaded=?, updated_at=?, revision=? WHERE deal_id=?""",
                    (
                        next_id, next_rating, next_text, next_created, next_updated,
                        next_author, int(next_loaded), self._now(), rev, deal_id,
                    ),
                )
                self._conn.commit()
            updated = self._order(
                self._conn.execute("SELECT * FROM orders WHERE deal_id=?", (deal_id,)).fetchone()
            )
            return updated, changed

    @staticmethod
    def _relist_receipt(row: sqlite3.Row | None) -> RelistReceipt | None:
        if row is None:
            return None
        return RelistReceipt(
            deal_id=row["deal_id"],
            source_item_id=row["source_item_id"],
            source_item_slug=row["source_item_slug"],
            published_item_id=row["published_item_id"],
            published_item_slug=row["published_item_slug"],
            priority_price=int(row["priority_price"]),
            priority_type=row["priority_type"],
            published_at=row["published_at"],
        )

    def get_relist_receipt(self, deal_id: str) -> RelistReceipt | None:
        with self._lock:
            return self._relist_receipt(
                self._conn.execute(
                    "SELECT * FROM relist_receipts WHERE deal_id=?",
                    (deal_id,),
                ).fetchone()
            )

    def claim_relist(
        self,
        deal_id: str,
        *,
        source_item_id: str,
        source_item_slug: str,
        priority_price: int,
        priority_type: str,
        listing_price: int,
        stale_before: str,
    ) -> tuple[OrderRow | None, bool]:
        """Atomically claim a relist attempt for one deal.

        A recent PUBLISHING claim cannot be taken over.  A stale/failed attempt
        may be resumed because publishing the same sold item ID is idempotent.
        A PUBLISHED state or immutable receipt can never be claimed again.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                receipt = self._conn.execute(
                    "SELECT 1 FROM relist_receipts WHERE deal_id=?",
                    (deal_id,),
                ).fetchone()
                row = self._order(
                    self._conn.execute(
                        "SELECT * FROM orders WHERE deal_id=?",
                        (deal_id,),
                    ).fetchone()
                )
                if row is None or receipt is not None or row.relist_state == "PUBLISHED":
                    self._conn.commit()
                    return row, False
                if (
                    row.relist_state == "PUBLISHING"
                    and row.relist_started_at
                    and row.relist_started_at >= stale_before
                ):
                    self._conn.commit()
                    return row, False

                now = self._now()
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET relist_state='PUBLISHING',
                       relist_source_item_id=?, relist_source_item_slug=?,
                       relist_priority_price=?, relist_priority_type=?,
                       relist_listing_price=?,
                       relist_started_at=?, relist_error='',
                       relist_attempts=relist_attempts+1,
                       updated_at=?, revision=? WHERE deal_id=?""",
                    (
                        source_item_id,
                        source_item_slug,
                        max(0, int(priority_price)),
                        priority_type,
                        max(0, int(listing_price)),
                        now,
                        now,
                        rev,
                        deal_id,
                    ),
                )
                self._conn.commit()
                updated = self._order(
                    self._conn.execute(
                        "SELECT * FROM orders WHERE deal_id=?",
                        (deal_id,),
                    ).fetchone()
                )
                return updated, True
            except Exception:
                self._conn.rollback()
                raise

    def mark_relist_draft(
        self,
        deal_id: str,
        *,
        source_item_id: str,
        draft_item_id: str,
        draft_item_slug: str,
    ) -> tuple[OrderRow | None, bool]:
        """Persist the only draft that this order is allowed to publish.

        Once a draft ID has been attached to an order, a retry may only resume
        that same draft. This closes the dangerous publish-retry window: an API
        timeout can never make the service publish a second item for the order.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                receipt = self._conn.execute(
                    "SELECT 1 FROM relist_receipts WHERE deal_id=?",
                    (deal_id,),
                ).fetchone()
                row = self._order(
                    self._conn.execute(
                        "SELECT * FROM orders WHERE deal_id=?",
                        (deal_id,),
                    ).fetchone()
                )
                if (
                    row is None
                    or receipt is not None
                    or row.relist_state == "PUBLISHED"
                    or row.relist_source_item_id != source_item_id
                    or not draft_item_id
                    or (
                        row.relist_draft_item_id
                        and row.relist_draft_item_id != draft_item_id
                    )
                ):
                    self._conn.commit()
                    return row, False

                now = self._now()
                rev = self._next_revision_locked()
                self._conn.execute(
                    """UPDATE orders SET relist_state='DRAFT_READY',
                       relist_draft_item_id=?, relist_draft_item_slug=?,
                       relist_draft_created_at=CASE
                           WHEN relist_draft_created_at='' THEN ?
                           ELSE relist_draft_created_at END,
                       relist_error='', updated_at=?, revision=?
                       WHERE deal_id=?""",
                    (
                        draft_item_id,
                        draft_item_slug,
                        now,
                        now,
                        rev,
                        deal_id,
                    ),
                )
                self._conn.commit()
                updated = self._order(
                    self._conn.execute(
                        "SELECT * FROM orders WHERE deal_id=?",
                        (deal_id,),
                    ).fetchone()
                )
                return updated, True
            except Exception:
                self._conn.rollback()
                raise

    def mark_relist_published(
        self,
        deal_id: str,
        *,
        source_item_id: str,
        source_item_slug: str,
        published_item_id: str,
        published_item_slug: str,
        priority_price: int,
        priority_type: str,
        published_at: str = "",
    ) -> tuple[RelistReceipt, bool]:
        """Persist the one immutable success receipt for a source order."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                when = published_at or self._now()
                cur = self._conn.execute(
                    """INSERT OR IGNORE INTO relist_receipts
                       (deal_id,source_item_id,source_item_slug,published_item_id,
                        published_item_slug,priority_price,priority_type,published_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        deal_id,
                        source_item_id,
                        source_item_slug,
                        published_item_id,
                        published_item_slug,
                        max(0, int(priority_price)),
                        priority_type,
                        when,
                    ),
                )
                created = cur.rowcount > 0
                receipt = self._relist_receipt(
                    self._conn.execute(
                        "SELECT * FROM relist_receipts WHERE deal_id=?",
                        (deal_id,),
                    ).fetchone()
                )
                assert receipt is not None

                current = self._order(
                    self._conn.execute(
                        "SELECT * FROM orders WHERE deal_id=?",
                        (deal_id,),
                    ).fetchone()
                )
                if current is not None and (
                    current.relist_state != "PUBLISHED"
                    or current.relisted_item_id != receipt.published_item_id
                ):
                    rev = self._next_revision_locked()
                    now = self._now()
                    self._conn.execute(
                        """UPDATE orders SET relist_state='PUBLISHED',
                           relist_source_item_id=?, relist_source_item_slug=?,
                           relist_draft_item_id=CASE
                               WHEN relist_draft_item_id='' THEN ?
                               ELSE relist_draft_item_id END,
                           relist_draft_item_slug=CASE
                               WHEN relist_draft_item_slug='' THEN ?
                               ELSE relist_draft_item_slug END,
                           relisted_item_id=?, relisted_item_slug=?,
                           relist_priority_price=?, relist_priority_type=?,
                           relisted_at=?, relist_error='', updated_at=?, revision=?
                           WHERE deal_id=?""",
                        (
                            receipt.source_item_id,
                            receipt.source_item_slug,
                            receipt.published_item_id,
                            receipt.published_item_slug,
                            receipt.published_item_id,
                            receipt.published_item_slug,
                            receipt.priority_price,
                            receipt.priority_type,
                            receipt.published_at,
                            now,
                            rev,
                            deal_id,
                        ),
                    )
                self._conn.commit()
                return receipt, created
            except Exception:
                self._conn.rollback()
                raise

    def mark_relist_failed(self, deal_id: str, error: str) -> OrderRow | None:
        with self._lock:
            receipt = self._conn.execute(
                "SELECT 1 FROM relist_receipts WHERE deal_id=?",
                (deal_id,),
            ).fetchone()
            row = self._order(
                self._conn.execute(
                    "SELECT * FROM orders WHERE deal_id=?",
                    (deal_id,),
                ).fetchone()
            )
            if row is None or receipt is not None or row.relist_state == "PUBLISHED":
                return row
            rev = self._next_revision_locked()
            now = self._now()
            self._conn.execute(
                """UPDATE orders SET relist_state='FAILED', relist_error=?,
                   updated_at=?, revision=? WHERE deal_id=?""",
                ((error or "")[:500], now, rev, deal_id),
            )
            self._conn.commit()
            return self._order(
                self._conn.execute(
                    "SELECT * FROM orders WHERE deal_id=?",
                    (deal_id,),
                ).fetchone()
            )

    def add_event(
        self,
        event_key: str,
        deal_id: str,
        kind: str,
        title: str,
        body: str,
    ) -> tuple[EventRow, bool]:
        with self._lock:
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO events
                   (deal_id,ref_deal_id,kind,title,body,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (event_key, deal_id, kind, title, body, self._now()),
            )
            created = cur.rowcount > 0
            self._conn.commit()
            row = self._event(
                self._conn.execute("SELECT * FROM events WHERE deal_id=?", (event_key,)).fetchone()
            )
            assert row is not None
            return row, created

    def next_event(self, after: int) -> EventRow | None:
        with self._lock:
            return self._event(
                self._conn.execute(
                    "SELECT * FROM events WHERE id>? ORDER BY id ASC LIMIT 1",
                    (after,),
                ).fetchone()
            )

    def latest_event_id(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
            return int(row[0]) if row is not None else 0
