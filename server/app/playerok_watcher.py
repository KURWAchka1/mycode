from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from curl_cffi import CurlOpt
from curl_cffi.requests import AsyncSession

from PyPlayerokAPI.graphql import build_query_payload
from .db import OrderStore
from .processor import OrderProcessor
from .playerok_raw import RawPlayerokAPI

log = logging.getLogger(__name__)


ITEM_PAID_TEXT = "{{ITEM_PAID}}"
ITEM_SENT_TEXT = "{{ITEM_SENT}}"
DEAL_CONFIRMED_TEXT = "{{DEAL_CONFIRMED}}"
DEAL_CONFIRMED_AUTOMATICALLY_TEXT = "{{DEAL_CONFIRMED_AUTOMATICALLY}}"
DEAL_HAS_PROBLEM_TEXT = "{{DEAL_HAS_PROBLEM}}"
DEAL_PROBLEM_RESOLVED_TEXT = "{{DEAL_PROBLEM_RESOLVED}}"
DEAL_ROLLED_BACK_TEXT = "{{DEAL_ROLLED_BACK}}"
# Recover payments missed during a short restart/outage without replaying old history.
PAYMENT_LOOKBACK_SECONDS = 15 * 60
# A problem is operationally urgent, so permit a longer recovery window after a restart.
PROBLEM_ALERT_LOOKBACK_SECONDS = 2 * 60 * 60
# Cheap HTTP safety net. WebSocket normally wakes the scanner immediately.
FALLBACK_SCAN_SECONDS = 12.0
# Periodically inspect histories even when lastMessage did not visibly change.
FULL_HISTORY_SCAN_SECONDS = 60.0
FINANCIAL_REFRESH_SECONDS = 15 * 60.0
REVIEW_REFRESH_SECONDS = 5 * 60.0
REVIEW_RECENT_PAGES = 2
MAX_CHAT_PAGES = 3  # 72 latest messages; important when one buyer makes many orders in one chat.
AUTO_RELIST_SCAN_SECONDS = 12.0
AUTO_RELIST_MATCH_WINDOW_SECONDS = 45 * 60
AUTO_RELIST_RETRY_SECONDS = (15, 30, 60, 120, 240, 480, 900, 1200)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return default if value is None else value


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _direction_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    text = _text(name if name is not None else value).upper()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text if text in {"IN", "OUT"} else ""


def _status_name(value: Any) -> str:
    name = getattr(value, "name", None)
    text = _text(name if name is not None else value).upper()
    return text.rsplit(".", 1)[-1]


def _parse_dt(raw: Any) -> datetime | None:
    text = _text(raw)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _whole_money(raw: Any) -> int | None:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        return None
    return int(value)


@dataclass(frozen=True, slots=True)
class _AutoRelistMatch:
    published_item_id: str
    published_item_slug: str
    payment_id: str
    priority_price: int
    priority_type: str
    listing_price: int
    published_at: str
    published_dt: datetime


def _match_auto_relist(live_item: Any, paid_at: datetime) -> _AutoRelistMatch | None:
    """Match Playerok's own keep-in-sale publication without mutating it."""
    if _value(live_item, "keep_in_sale", False) is not True:
        return None
    if _status_name(_value(live_item, "status")) != "APPROVED":
        return None

    payment = _value(live_item, "status_payment")
    operation = _status_name(_value(payment, "operation"))
    if operation not in {"ITEM_PREMIUM_PRIORITY", "ITEM_DEFAULT_PRIORITY"}:
        return None
    if _status_name(_value(payment, "direction")) != "OUT":
        return None
    if _status_name(_value(payment, "status")) != "CONFIRMED":
        return None

    payment_id = _text(_value(payment, "id"))
    published_item_id = _text(_value(live_item, "id"))
    published_item_slug = _text(_value(live_item, "slug"))
    published_at = _text(_value(live_item, "approval_date"))
    published_dt = _parse_dt(published_at)
    priority_price = _whole_money(_value(payment, "value"))
    listing_price = _whole_money(
        _value(live_item, "raw_price", _value(live_item, "price", 0))
    )
    if (
        not payment_id
        or not published_item_id
        or not published_item_slug
        or published_dt is None
        or priority_price is None
    ):
        return None

    delta = (published_dt - paid_at).total_seconds()
    if delta < -30 or delta > AUTO_RELIST_MATCH_WINDOW_SECONDS:
        return None

    priority_type = (
        "PREMIUM" if operation == "ITEM_PREMIUM_PRIORITY" else "DEFAULT"
    )
    return _AutoRelistMatch(
        published_item_id=published_item_id,
        published_item_slug=published_item_slug,
        payment_id=payment_id,
        priority_price=priority_price,
        priority_type=priority_type,
        listing_price=listing_price or 0,
        published_at=published_at,
        published_dt=published_dt,
    )


class PlayerokOrderWatcher:
    """Reliable paid-order watcher independent of PyPlayerokAPI.stream.

    Design:
      * GraphQL WebSocket is only a low-latency *signal* that something changed.
      * HTTP chat/message data is the source of truth.
      * A 12-second fallback scan recovers missed WebSocket events.
      * Payment identity is deal_id, never chat_id. Therefore several purchases
        by the same buyer in the same chat are processed independently.
      * When a chat changes, up to 72 latest messages are inspected, so a quick
        buyer message cannot overwrite {{ITEM_PAID}} before we notice it.
      * Problem, resolution and rollback markers are tracked per deal with actor data.
      * SQLite remains the final dedupe layer.
    """

    def __init__(
        self,
        account: Any,
        processor: OrderProcessor,
        store: OrderStore,
        own_user_id: str,
    ) -> None:
        self.account = account
        self.processor = processor
        self.store = store
        self.own_user_id = own_user_id
        self.raw = RawPlayerokAPI(account, own_user_id)

        self._running = False
        self._scan_requested = asyncio.Event()
        self._scan_lock = asyncio.Lock()
        self._ws_send_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[Any]] = []
        self._last_message_ids: dict[str, str] = {}
        self._last_full_scan = 0.0
        self._http_ready_logged = False
        self._ws: Any = None
        self._session: AsyncSession | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        # v11 migration: classify historical cached deals once. This uses the
        # deals endpoint only during startup and writes the result to SQLite, so
        # Android tab switches never hit Playerok and normal runtime load stays
        # unchanged. Failures are non-fatal; new events are still classified
        # directly from deal.direction.
        try:
            await self._backfill_directions()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Historical deal direction backfill failed; continuing")
        try:
            await self._backfill_progress()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Historical deal progress backfill failed; continuing")
        try:
            await self._backfill_financials()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Historical seller financial backfill failed; continuing")
        self._scan_requested.set()
        self._tasks = [
            asyncio.create_task(self._websocket_forever(), name="playerok-ws-signal"),
            asyncio.create_task(self._scan_forever(), name="playerok-order-scan"),
            asyncio.create_task(self._financials_forever(), name="playerok-financial-refresh"),
            asyncio.create_task(self._reviews_forever(), name="playerok-review-refresh"),
            asyncio.create_task(self._buyer_fields_backfill_once(), name="playerok-buyer-fields-backfill"),
            asyncio.create_task(self._auto_relists_forever(), name="playerok-auto-relist-detect"),
        ]

    async def _backfill_directions(self) -> None:
        unresolved_rows = self.store.list_orders_needing_direction(limit=500)
        unresolved = {row.deal_id for row in unresolved_rows}
        if not unresolved:
            return

        initial = len(unresolved)
        # A handful of paginated list calls classifies most historical orders
        # much more cheaply than one GraphQL request per deal.
        for direction in ("OUT", "IN"):
            cursor: str | None = None
            for _ in range(5):
                page = await self.raw.get_deals(
                    count=24,
                    direction_name=direction,
                    after_cursor=cursor,
                )
                for deal in list(_value(page, "deals", []) or []):
                    deal_id = _text(_value(deal, "id"))
                    if deal_id in unresolved:
                        self.store.set_direction(deal_id, direction)
                        unresolved.discard(deal_id)
                if not unresolved:
                    break
                info = _value(page, "page_info")
                if not info or not bool(_value(info, "has_next_page", False)):
                    break
                next_cursor = _text(_value(info, "end_cursor"))
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
            if not unresolved:
                break

        # Old orders can fall outside the first pages. Resolve a bounded tail
        # individually once; this is startup-only and capped to protect a small VPS.
        for deal_id in list(unresolved)[:40]:
            try:
                deal = await self.raw.get_deal(deal_id)
                direction = _direction_name(_value(deal, "direction"))
                if direction:
                    self.store.set_direction(deal_id, direction)
                    unresolved.discard(deal_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.debug("Direction backfill could not resolve deal=%s", deal_id, exc_info=True)

        log.info(
            "Deal direction backfill: classified=%d unresolved=%d",
            initial - len(unresolved),
            len(unresolved),
        )

    async def _backfill_progress(self) -> None:
        """Refresh lifecycle for cached deals without replaying notifications."""
        updated = 0
        review_details: list[str] = []
        for direction in ("OUT", "IN"):
            cursor: str | None = None
            for _ in range(5):
                page = await self.raw.get_deals(
                    count=24,
                    direction_name=direction,
                    after_cursor=cursor,
                )
                for deal in list(_value(page, "deals", []) or []):
                    deal_id = _text(_value(deal, "id"))
                    if not deal_id or self.store.get(deal_id) is None:
                        continue
                    self.processor.persist_review(deal_id, deal, details_loaded=False)
                    testimonial = _value(deal, "testimonial") or _value(deal, "review")
                    current = self.store.get(deal_id)
                    if testimonial is not None and current is not None and not current.review_details_loaded:
                        review_details.append(deal_id)
                    status = _status_name(_value(deal, "status"))
                    _, changed = self.store.set_deal_progress(
                        deal_id,
                        deal_status=status,
                        seller_fulfilled=status in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"},
                        recipient_confirmed=status in {"CONFIRMED", "CONFIRMED_AUTOMATICALLY"},
                        recipient_at=_text(_value(deal, "completed_at")),
                        recipient_automatic=status == "CONFIRMED_AUTOMATICALLY",
                    )
                    if changed:
                        updated += 1
                info = _value(page, "page_info")
                if not info or not bool(_value(info, "has_next_page", False)):
                    break
                next_cursor = _text(_value(info, "end_cursor"))
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
        await self._refresh_review_details(review_details, reason="startup-backfill", limit=60)
        log.info("Deal progress backfill: updated=%d", updated)

    async def _backfill_buyer_fields(self) -> None:
        """Load dynamic checkout fields once without adding steady VPS load."""
        rows = self.store.list_orders_needing_buyer_fields(limit=100)
        updated = 0
        failed = 0
        for row in rows:
            try:
                deal = await self.raw.get_deal(row.deal_id)
                if self.processor.persist_buyer_fields(
                    row.deal_id, deal, details_loaded=True
                ):
                    updated += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                failed += 1
                log.debug(
                    "Buyer fields backfill failed deal=%s", row.deal_id, exc_info=True
                )
            await asyncio.sleep(0.2)
        if rows:
            log.info(
                "Buyer fields backfill: checked=%d updated=%d failed=%d",
                len(rows),
                updated,
                failed,
            )

    async def _buyer_fields_backfill_once(self) -> None:
        """Fill historical fields after live monitoring has already started."""
        await asyncio.sleep(2)
        try:
            await self._backfill_buyer_fields()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Historical buyer fields backfill failed; live monitoring continues")

    async def _refresh_review_details(
        self,
        deal_ids: list[str],
        *,
        reason: str,
        limit: int = 24,
    ) -> None:
        unique = list(dict.fromkeys(deal_ids))[:limit]
        loaded = 0
        failed = 0
        for deal_id in unique:
            try:
                deal = await self.raw.get_deal(deal_id)
                if self.processor.persist_review(deal_id, deal, details_loaded=True):
                    loaded += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                failed += 1
                log.debug("Review detail refresh failed deal=%s", deal_id, exc_info=True)
            await asyncio.sleep(0.25)
        if unique:
            log.info(
                "Review detail refresh reason=%s checked=%d updated=%d failed=%d",
                reason,
                len(unique),
                loaded,
                failed,
            )

    async def _refresh_recent_reviews(self) -> None:
        detail_ids: list[str] = []
        summaries = 0
        for direction in ("OUT", "IN"):
            cursor: str | None = None
            for _ in range(REVIEW_RECENT_PAGES):
                page = await self.raw.get_deals(
                    count=24,
                    direction_name=direction,
                    after_cursor=cursor,
                )
                for deal in list(_value(page, "deals", []) or []):
                    deal_id = _text(_value(deal, "id"))
                    if not deal_id or self.store.get(deal_id) is None:
                        continue
                    testimonial = _value(deal, "testimonial") or _value(deal, "review")
                    if testimonial is None:
                        continue
                    summaries += 1
                    self.processor.persist_review(deal_id, deal, details_loaded=False)
                    current = self.store.get(deal_id)
                    if current is not None and not current.review_details_loaded:
                        detail_ids.append(deal_id)
                info = _value(page, "page_info")
                if not info or not bool(_value(info, "has_next_page", False)):
                    break
                next_cursor = _text(_value(info, "end_cursor"))
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
        await self._refresh_review_details(detail_ids, reason="new-testimonial")
        log.info("Recent review refresh: testimonials=%d new_details=%d", summaries, len(set(detail_ids)))

    async def _reviews_forever(self) -> None:
        while self._running:
            await asyncio.sleep(REVIEW_REFRESH_SECONDS)
            try:
                await self._refresh_recent_reviews()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Recent review refresh failed; will retry later")

    async def _refresh_financial_rows(self, rows: list[Any], *, reason: str) -> None:
        updated = 0
        failed = 0
        for row in rows:
            try:
                deal = await self.raw.get_deal(row.deal_id)
                if self.processor.persist_seller_financials(row.deal_id, deal):
                    updated += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                failed += 1
                log.debug(
                    "Seller financial refresh failed deal=%s",
                    row.deal_id,
                    exc_info=True,
                )
            await asyncio.sleep(0.2)
        log.info(
            "Seller financial refresh reason=%s checked=%d updated=%d failed=%d",
            reason,
            len(rows),
            updated,
            failed,
        )

    async def _backfill_financials(self) -> None:
        rows = self.store.list_orders_needing_financials(limit=100)
        if rows:
            await self._refresh_financial_rows(rows, reason="startup-backfill")

    async def _financials_forever(self) -> None:
        while self._running:
            await asyncio.sleep(FINANCIAL_REFRESH_SECONDS)
            rows = self.store.list_orders_with_pending_financials(limit=50)
            if rows:
                await self._refresh_financial_rows(rows, reason="pending-status")

    @staticmethod
    def _auto_relist_retry_delay(attempts: int) -> int:
        index = max(0, min(int(attempts), len(AUTO_RELIST_RETRY_SECONDS) - 1))
        return AUTO_RELIST_RETRY_SECONDS[index]

    async def _detect_auto_relists_once(self) -> None:
        due = self.store.list_due_auto_relist_checks(limit=8)
        if not due:
            return

        grouped: dict[str, list[Any]] = {}
        for candidate in due:
            grouped.setdefault(candidate.source_item_slug, []).append(candidate)

        for slug, due_for_slug in grouped.items():
            try:
                live_item = await self.raw.get_item_by_slug(slug)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                for candidate in due_for_slug:
                    self.store.defer_auto_relist_check(
                        candidate.deal_id,
                        delay_seconds=self._auto_relist_retry_delay(candidate.attempts),
                        error=f"ITEM_READ_{type(exc).__name__}",
                    )
                log.debug(
                    "Auto-relist item read failed slug=%s", slug, exc_info=True
                )
                continue

            compatible: list[tuple[float, Any, _AutoRelistMatch]] = []
            for candidate in self.store.list_open_auto_relist_checks(slug):
                paid_at = _parse_dt(candidate.payment_created_at)
                if paid_at is None:
                    continue
                match = _match_auto_relist(live_item, paid_at)
                if match is not None:
                    compatible.append(
                        ((match.published_dt - paid_at).total_seconds(), candidate, match)
                    )

            selected_deal_id = ""
            if compatible:
                # If the same permanent item is bought twice quickly, bind the
                # current Playerok payment to the closest preceding purchase.
                _delta, candidate, match = min(compatible, key=lambda entry: entry[0])
                selected_deal_id = candidate.deal_id
                order = self.store.get(candidate.deal_id)
                if order is not None:
                    try:
                        receipt, _created = self.store.mark_relist_published(
                            candidate.deal_id,
                            source_item_id=candidate.source_item_id,
                            source_item_slug=candidate.source_item_slug,
                            published_item_id=match.published_item_id,
                            published_item_slug=match.published_item_slug,
                            priority_price=match.priority_price,
                            priority_type=match.priority_type,
                            published_at=match.published_at,
                            receipt_source="PLAYEROK_AUTO",
                            payment_id=match.payment_id,
                            listing_price=match.listing_price,
                        )
                    except ValueError:
                        self.store.defer_auto_relist_check(
                            candidate.deal_id,
                            delay_seconds=self._auto_relist_retry_delay(candidate.attempts),
                            error="PAYMENT_ALREADY_LINKED",
                        )
                        log.warning(
                            "Ignored reused Playerok auto-relist payment deal=%s payment=%s",
                            candidate.deal_id,
                            match.payment_id,
                        )
                    else:
                        self.store.complete_auto_relist_check(candidate.deal_id)
                        if (
                            receipt.source == "PLAYEROK_AUTO"
                            and receipt.payment_id == match.payment_id
                        ):
                            await self.processor.bus.publish_auto_relist(
                                order,
                                payment_id=match.payment_id,
                                priority_price=match.priority_price,
                            )
                            log.info(
                                "Playerok auto-relist detected deal=%s item=%s fee=%s",
                                candidate.deal_id,
                                match.published_item_id,
                                match.priority_price,
                            )
                else:
                    self.store.complete_auto_relist_check(candidate.deal_id)

            for candidate in due_for_slug:
                if candidate.deal_id == selected_deal_id:
                    continue
                self.store.defer_auto_relist_check(
                    candidate.deal_id,
                    delay_seconds=self._auto_relist_retry_delay(candidate.attempts),
                    error="NOT_AUTO_RELISTED_YET",
                )
            await asyncio.sleep(0.2)

    async def _auto_relists_forever(self) -> None:
        # This loop is intentionally bounded by the persisted eight-attempt
        # schedule. It never scans historical orders or performs Playerok writes.
        await asyncio.sleep(3)
        while self._running:
            try:
                await self._detect_auto_relists_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Playerok auto-relist detection failed")
            await asyncio.sleep(AUTO_RELIST_SCAN_SECONDS)

    async def stop(self) -> None:
        self._running = False
        self._scan_requested.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    def request_scan(self) -> None:
        self._scan_requested.set()

    async def _scan_forever(self) -> None:
        # Initial recovery scan is intentionally full, but still limited by the
        # 15-minute payment lookback to avoid notifying ancient purchases.
        first = True
        while self._running:
            by_signal = False
            try:
                await asyncio.wait_for(
                    self._scan_requested.wait(),
                    timeout=FALLBACK_SCAN_SECONDS,
                )
                by_signal = True
            except TimeoutError:
                pass
            self._scan_requested.clear()

            now = time.monotonic()
            full_history = first or (now - self._last_full_scan >= FULL_HISTORY_SCAN_SECONDS)
            if full_history:
                self._last_full_scan = now
            first = False

            try:
                await self._scan_once(full_history=full_history, reason="ws" if by_signal else "fallback")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Playerok order scan failed")

    async def _scan_once(self, *, full_history: bool, reason: str) -> None:
        async with self._scan_lock:
            chats_page = await self._get_chats_with_retry()
            chats = list(_value(chats_page, "chats", []) or [])
            if not self._http_ready_logged:
                log.info("Playerok raw HTTP scan OK; enum-model bypass active; chats=%d", len(chats))
                self._http_ready_logged = True
            if not chats:
                log.debug("Playerok scan reason=%s: no chats", reason)
                return

            now_utc = datetime.now(timezone.utc)
            candidates: list[Any] = []

            for chat in chats:
                chat_id = _text(_value(chat, "id"))
                if not chat_id:
                    continue
                last = _value(chat, "last_message")
                last_id = _text(_value(last, "id"))
                previous_id = self._last_message_ids.get(chat_id)
                changed = bool(last_id and last_id != previous_id)
                self._last_message_ids[chat_id] = last_id

                last_is_paid = _text(_value(last, "text")) == ITEM_PAID_TEXT
                last_dt = _parse_dt(_value(last, "created_at"))
                recently_active = bool(
                    last_dt
                    and (now_utc - last_dt).total_seconds() <= PAYMENT_LOOKBACK_SECONDS
                )

                # On a normal pass, query history only for chats that changed or
                # show a paid system message. Once per minute also inspect recent
                # chat histories to recover an event lost by both WS and lastMessage.
                if changed or last_is_paid or (full_history and recently_active):
                    candidates.append(chat)

            # On the very first scan previous_id is unknown, so recent chats are
            # naturally candidates. Cap only by Playerok's get_chats page (24).
            for chat in candidates:
                try:
                    await self._scan_chat(chat, now_utc)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Failed to inspect Playerok chat=%s", _text(_value(chat, "id")))

            log.debug(
                "Playerok scan reason=%s full=%s chats=%d candidates=%d",
                reason,
                full_history,
                len(chats),
                len(candidates),
            )

    async def _get_chats_with_retry(self) -> Any:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return await self.raw.get_chats(count=24, type_name="PM")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    await asyncio.sleep(1.0 + attempt * 1.5)
        assert last_exc is not None
        raise last_exc

    async def _get_recent_messages(self, chat_id: str) -> list[Any]:
        result: list[Any] = []
        seen: set[str] = set()
        cursor: str | None = None

        for _ in range(MAX_CHAT_PAGES):
            page = await self.raw.get_chat_messages(
                chat_id=chat_id,
                count=24,
                after_cursor=cursor,
            )
            messages = list(_value(page, "messages", []) or [])
            for msg in messages:
                msg_id = _text(_value(msg, "id"))
                key = msg_id or f"anon-{id(msg)}"
                if key not in seen:
                    seen.add(key)
                    result.append(msg)

            info = _value(page, "page_info")
            if not info or not bool(_value(info, "has_next_page", False)):
                break
            next_cursor = _text(_value(info, "end_cursor"))
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            # No reason to request deeper pages once the oldest fetched message
            # is outside the recovery window.
            parsed = [d for m in result if (d := _parse_dt(_value(m, "created_at"))) is not None]
            if parsed and (datetime.now(timezone.utc) - min(parsed)).total_seconds() > max(PAYMENT_LOOKBACK_SECONDS, PROBLEM_ALERT_LOOKBACK_SECONDS):
                break

        return result

    async def _scan_chat(self, chat: Any, now_utc: datetime) -> None:
        chat_id = _text(_value(chat, "id"))
        if not chat_id:
            return

        messages = await self._get_recent_messages(chat_id)
        last = _value(chat, "last_message")
        if last is not None:
            last_id = _text(_value(last, "id"))
            if not any(_text(_value(m, "id")) == last_id for m in messages):
                messages.append(last)

        # Oldest -> newest is critical when the same buyer has several purchases
        # and/or problem state changes in one Playerok chat.
        messages.sort(
            key=lambda m: _parse_dt(_value(m, "created_at"))
            or datetime.min.replace(tzinfo=timezone.utc)
        )

        for msg in messages:
            marker = _text(_value(msg, "text"))
            if marker not in {
                ITEM_PAID_TEXT,
                ITEM_SENT_TEXT,
                DEAL_CONFIRMED_TEXT,
                DEAL_CONFIRMED_AUTOMATICALLY_TEXT,
                DEAL_HAS_PROBLEM_TEXT,
                DEAL_PROBLEM_RESOLVED_TEXT,
                DEAL_ROLLED_BACK_TEXT,
            }:
                continue

            event_at = _parse_dt(_value(msg, "created_at"))
            age_seconds = (now_utc - event_at).total_seconds() if event_at is not None else None

            deal = _value(msg, "deal")
            deal_id = _text(_value(deal, "id"))
            if not deal_id:
                # Never infer a deal from chat_id: one buyer can place many orders
                # in exactly the same chat. A later scan normally receives it.
                log.warning(
                    "%s has no deal id yet; chat=%s message=%s; will retry",
                    marker,
                    chat_id,
                    _text(_value(msg, "id")),
                )
                continue

            if marker == ITEM_PAID_TEXT:
                if age_seconds is not None and age_seconds > PAYMENT_LOOKBACK_SECONDS:
                    continue
                if self.store.get(deal_id) is None:
                    deal = await self._fresh_deal(deal_id, fallback=deal)
                event = SimpleNamespace(deal=deal, chat=chat, message=msg)
                await self.processor.handle_item_paid(event)
                continue

            # Deal-state markers are tied to the deal object in Playerok's own event
            # model. Refresh the deal to populate item/buyer information even when
            # the original payment predates this monitor installation.
            deal = await self._fresh_deal(deal_id, fallback=deal)
            event = SimpleNamespace(deal=deal, chat=chat, message=msg)
            if marker in {
                ITEM_SENT_TEXT,
                DEAL_CONFIRMED_TEXT,
                DEAL_CONFIRMED_AUTOMATICALLY_TEXT,
            }:
                await self.processor.handle_deal_progress(event, marker)
                continue
            notify = age_seconds is None or age_seconds <= PROBLEM_ALERT_LOOKBACK_SECONDS
            if marker == DEAL_ROLLED_BACK_TEXT:
                await self.processor.handle_deal_rolled_back(event, notify=notify)
            else:
                await self.processor.handle_deal_problem(
                    event,
                    active=(marker == DEAL_HAS_PROBLEM_TEXT),
                    notify=notify,
                )

    async def _fresh_deal(self, deal_id: str, fallback: Any) -> Any:
        for attempt in range(3):
            try:
                return await self.raw.get_deal(deal_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.8 + attempt * 0.8)
        log.warning("Could not refresh deal=%s; using message copy", deal_id)
        return fallback

    async def _websocket_forever(self) -> None:
        session_kwargs: dict[str, Any] = {
            "impersonate": "chrome",
            "curl_options": {
                CurlOpt.CAINFO: self.account.transport._tmp_cert_path,
            },
        }
        proxy = getattr(self.account.transport, "_proxy_string", None)
        if proxy:
            session_kwargs["proxy"] = proxy
        self._session = AsyncSession(**session_kwargs)

        while self._running:
            try:
                await self._ws_connect_and_receive()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Playerok websocket disconnected: %s", exc)
            if self._running:
                await asyncio.sleep(3)

    async def _ws_connect_and_receive(self) -> None:
        assert self._session is not None
        headers = {
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "connection": "Upgrade",
            "origin": "https://playerok.com",
            "pragma": "no-cache",
            "sec-websocket-extensions": "permessage-deflate; client_max_window_bits",
            "Sec-WebSocket-Protocol": "graphql-transport-ws",
            "cookie": f"token={self.account.token}",
            "user-agent": self.account.user_agent,
        }

        log.info("Connecting Playerok websocket...")
        self._ws = await self._session.ws_connect(
            url="wss://ws.playerok.com/graphql",
            headers=headers,
        )
        await self._ws_send({
            "type": "connection_init",
            "payload": {
                "x-gql-op": "ws-subscription",
                "x-gql-path": "/self.chats/[id]",
                "x-timezone-offset": -180,
            },
        })

        while self._running:
            try:
                data, opcode = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
            except TimeoutError:
                # Keep the graphql-transport-ws connection warm without forcing a
                # reconnect when the account simply has no activity.
                await self._ws_send({"type": "ping"})
                continue
            if opcode == 8:
                raise ConnectionError("Playerok websocket closed")
            if opcode != 1 or not data:
                continue
            raw = data.decode("utf-8", "replace") if isinstance(data, (bytes, bytearray)) else str(data)
            await self._handle_ws_message(raw)

    async def _handle_ws_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type")
        if msg_type == "connection_ack":
            await self._subscribe_updates()
            log.info("Playerok websocket connected; update subscriptions active")
            self.request_scan()
            return
        if msg_type == "ping":
            await self._ws_send({"type": "pong"})
            return
        if msg_type in {"pong", "complete"}:
            return

        payload = (data.get("payload") or {}).get("data") or {}
        # We deliberately use the WS event only as a wake-up signal. The HTTP
        # scan then reads all payment messages, including several deals in one chat.
        if "chatUpdated" in payload or "userUpdated" in payload or "chatMessageCreated" in payload:
            self.request_scan()

    async def _subscribe_updates(self) -> None:
        # The JWT `sub` claim is already the authenticated account id. Avoid
        # PyPlayerokAPI's profile APQ here: Playerok rotates that hash and a
        # stale SDK hash would otherwise force a WebSocket reconnect loop.
        user_id = self.own_user_id
        if not user_id:
            user_id = await self.account.get_account_property("id")
        chat_updated = build_query_payload(
            operation_name="chatUpdated",
            query_key="chatUpdated",
            variables={
                "filter": {"userId": user_id},
                "showForbiddenImage": True,
            },
        )
        user_updated = build_query_payload(
            operation_name="userUpdated",
            query_key="userUpdated",
            variables={"userId": user_id},
        )
        for payload in (chat_updated, user_updated):
            await self._ws_send({
                "id": str(uuid.uuid4()),
                "payload": {"extensions": {}, **payload},
                "type": "subscribe",
            })

    async def _ws_send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            return
        async with self._ws_send_lock:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
