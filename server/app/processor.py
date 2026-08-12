from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from types import SimpleNamespace

from PyPlayerokAPI.account import AccountClient

from .config import Settings
from .db import OrderRow, OrderStore
from .event_bus import EventBus
from .playerok_raw import RawPlayerokAPI

log = logging.getLogger(__name__)

ITEM_PAID_TEXT = "{{ITEM_PAID}}"
ITEM_SENT_TEXT = "{{ITEM_SENT}}"
DEAL_CONFIRMED_TEXT = "{{DEAL_CONFIRMED}}"
DEAL_CONFIRMED_AUTOMATICALLY_TEXT = "{{DEAL_CONFIRMED_AUTOMATICALLY}}"


def _value(obj: Any, *names: str) -> Any:
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def _direction_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    text = _text(name if name is not None else value).upper()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text if text in {"IN", "OUT"} else ""


def _enum_name(value: Any) -> str:
    if value is None:
        return ""
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


class OrderProcessor:
    def __init__(
        self,
        settings: Settings,
        store: OrderStore,
        bus: EventBus,
        account: AccountClient,
        own_user_id: str,
    ) -> None:
        self.settings, self.store, self.bus, self.account = settings, store, bus, account
        self.own_user_id = own_user_id
        self.raw = RawPlayerokAPI(account, own_user_id)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @staticmethod
    def _buyer_fields_json(deal: Any) -> str:
        raw_fields = _value(deal, "obtaining_fields", "obtainingFields")
        if raw_fields is None:
            return ""
        fields: list[dict[str, object]] = []
        for index, field in enumerate(list(raw_fields)[:24], start=1):
            label = _text(_value(field, "label", "name"))[:160]
            value = _value(field, "value")
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            else:
                rendered = _text(value)
            rendered = rendered[:8000]
            if not rendered:
                continue
            fields.append(
                {
                    "label": label or f"Поле {index}",
                    "value": rendered,
                    "copyable": bool(_value(field, "copyable")),
                }
            )
        return json.dumps(fields, ensure_ascii=False, separators=(",", ":"))

    def persist_buyer_fields(
        self,
        deal_id: str,
        deal: Any,
        *,
        details_loaded: bool = False,
    ) -> bool:
        fields_json = self._buyer_fields_json(deal)
        if not fields_json and details_loaded:
            # A detailed response with no obtainingFields is a valid, final
            # result. Persist [] so this order is not fetched on every restart.
            fields_json = "[]"
        if not fields_json:
            return False
        _, changed = self.store.set_buyer_fields(deal_id, fields_json)
        return changed

    def _extract_order(self, event: Any) -> tuple[str, str, str, str, str, str, str]:
        deal = _value(event, "deal")
        chat = _value(event, "chat")
        chat_id = _text(_value(chat, "id"))
        deal_id = _text(_value(deal, "id"))
        if not deal_id:
            message = _value(event, "message")
            raise ValueError(
                f"Playerok event without deal id chat={chat_id} message={_text(_value(message, 'id'))}"
            )

        item = _value(deal, "item")
        item_name = _text(_value(item, "name", "title")) or _text(
            _value(deal, "item_name", "title", "name")
        )
        raw_price = _value(deal, "price", "amount")
        if raw_price is None and item is not None:
            raw_price = _value(item, "price")
        price = _text(raw_price)
        if (
            price
            and "₽" not in price
            and "руб" not in price.lower()
            and price.replace(".", "", 1).isdigit()
        ):
            price += " ₽"

        buyer = ""
        try:
            for user in _value(chat, "users") or []:
                uid = _text(_value(user, "id"))
                if self.own_user_id and uid == self.own_user_id:
                    continue
                buyer = _text(_value(user, "username", "name"))
                if buyer:
                    break
        except Exception:
            pass
        if not buyer:
            deal_user = _value(deal, "user")
            uid = _text(_value(deal_user, "id"))
            if not self.own_user_id or uid != self.own_user_id:
                buyer = _text(_value(deal_user, "username", "name"))

        buyer_comment = _text(_value(deal, "comment_from_buyer", "commentFromBuyer"))
        direction = _direction_name(_value(deal, "direction"))
        return deal_id, chat_id, item_name, price, buyer, buyer_comment, direction

    def _payment_fields(self, event: Any) -> tuple[str, str]:
        message = _value(event, "message")
        return (
            _text(_value(message, "id")),
            _text(_value(message, "created_at", "createdAt")),
        )

    @staticmethod
    def _seller_financial_fields(event: Any) -> tuple[str, str, str]:
        deal = _value(event, "deal")
        if _direction_name(_value(deal, "direction")) != "OUT":
            return "", "", ""
        transaction = _value(deal, "transaction")
        if transaction is None:
            return "", "", ""
        return (
            _text(_value(transaction, "value")),
            _enum_name(_value(transaction, "status")),
            _text(_value(transaction, "status_expiration_date", "statusExpirationDate")),
        )

    def persist_seller_financials(self, deal_id: str, deal: Any) -> bool:
        amount, status, available_at = self._seller_financial_fields(
            SimpleNamespace(deal=deal)
        )
        if not amount and not status:
            return False
        _, changed = self.store.set_seller_financials(
            deal_id,
            amount=amount,
            status=status,
            available_at=available_at,
        )
        return changed

    def persist_review(self, deal_id: str, deal: Any, *, details_loaded: bool) -> bool:
        """Store the testimonial embedded into a deal response, if present."""
        review = _value(deal, "review", "testimonial")
        if review is None:
            return False
        raw_rating = _value(review, "rating")
        try:
            rating = int(raw_rating or 0)
        except (TypeError, ValueError):
            rating = 0
        creator = _value(review, "creator", "user")
        author = _text(_value(creator, "username", "display_name", "displayName", "name"))
        # A deal summary also exposes ``testimonial`` but omits its text/date.
        # Treat the response as detailed only when at least one full-only field
        # is actually present, even if a caller had to fall back to a summary.
        details_loaded = bool(details_loaded and (
            _value(review, "created_at", "createdAt") is not None
            or _value(review, "updated_at", "updatedAt") is not None
            or creator is not None
        ))
        _, changed = self.store.set_review(
            deal_id,
            review_id=_text(_value(review, "id")),
            rating=rating,
            text=_text(_value(review, "text")),
            created_at=_text(_value(review, "created_at", "createdAt")),
            updated_at=_text(_value(review, "updated_at", "updatedAt")),
            author=author,
            details_loaded=details_loaded,
        )
        return changed

    async def request_fulfillment(self, deal_id: str) -> dict[str, object]:
        """Confirm this account's sale exactly once after explicit app action."""
        clean_id = (deal_id or "").strip()
        if not clean_id:
            return {"ok": False, "code": "DEAL_REQUIRED", "message": "Не указан заказ"}

        async with self._locks[clean_id]:
            row = self.store.get(clean_id)
            if row is None:
                return {"ok": False, "code": "DEAL_NOT_FOUND", "message": "Заказ не найден в базе VPS"}
            if row.direction != "OUT":
                return {
                    "ok": False,
                    "code": "NOT_A_SALE",
                    "message": "Подтвердить выполнение можно только для вашей продажи",
                }
            if row.rolled_back:
                return {"ok": False, "code": "ROLLED_BACK", "message": "По заказу уже оформлен возврат"}
            if row.problem_active:
                return {
                    "ok": False,
                    "code": "PROBLEM_ACTIVE",
                    "message": "Сначала решите активную проблему по заказу",
                }

            try:
                deal = await self.raw.get_deal(clean_id)
            except Exception:
                log.exception("Fulfillment preflight failed deal=%s", clean_id)
                return {
                    "ok": False,
                    "code": "PLAYEROK_LOOKUP_FAILED",
                    "message": "Не удалось проверить заказ на Playerok. Повторите позже",
                }

            direction = _direction_name(_value(deal, "direction"))
            status = _enum_name(_value(deal, "status"))
            if direction != "OUT":
                return {
                    "ok": False,
                    "code": "NOT_A_SALE",
                    "message": "Playerok не подтвердил, что это ваша продажа",
                }
            if status == "ROLLED_BACK":
                return {"ok": False, "code": "ROLLED_BACK", "message": "По заказу уже оформлен возврат"}
            if bool(_value(deal, "has_problem", "hasProblem")):
                return {
                    "ok": False,
                    "code": "PROBLEM_ACTIVE",
                    "message": "На Playerok открыта проблема по этому заказу",
                }

            already_fulfilled = status in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"}
            if not already_fulfilled:
                if status not in {"PAID", "PENDING"}:
                    return {
                        "ok": False,
                        "code": "STATUS_NOT_FULFILLABLE",
                        "message": f"Заказ нельзя подтвердить в статусе {status or 'неизвестен'}",
                    }
                try:
                    deal = await self.raw.update_deal_status(clean_id, "SENT")
                except Exception as exc:
                    # A mutation can succeed even if its HTTP response is lost.
                    try:
                        verified = await self.raw.get_deal(clean_id)
                    except Exception:
                        verified = None
                    verified_status = _enum_name(_value(verified, "status"))
                    if verified_status not in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"}:
                        log.exception("Playerok fulfillment failed deal=%s", clean_id)
                        return {
                            "ok": False,
                            "code": "PLAYEROK_UPDATE_FAILED",
                            "message": "Playerok не подтвердил выполнение. Повтор безопасен",
                        }
                    deal = verified
                    status = verified_status
                    log.warning("Recovered accepted Playerok fulfillment deal=%s", clean_id)
                else:
                    status = _enum_name(_value(deal, "status"))
                    if status not in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"}:
                        return {
                            "ok": False,
                            "code": "PLAYEROK_UPDATE_FAILED",
                            "message": "Playerok не вернул подтверждённый статус выполнения",
                        }

            self.persist_buyer_fields(clean_id, deal, details_loaded=True)
            self.persist_review(clean_id, deal, details_loaded=True)
            recipient_confirmed = status in {"CONFIRMED", "CONFIRMED_AUTOMATICALLY"}
            updated, _ = self.store.set_deal_progress(
                clean_id,
                deal_status=status,
                seller_fulfilled=True,
                seller_at=datetime.now(timezone.utc).isoformat(),
                recipient_confirmed=recipient_confirmed,
                recipient_at=_text(_value(deal, "completed_at", "completedAt")),
                recipient_automatic=status == "CONFIRMED_AUTOMATICALLY",
                actor_role="USER",
                actor_relation="SELF",
            )
            if updated is not None and updated.fulfillment_reply_eligible and not updated.fulfillment_reply_sent:
                await self.ensure_fulfillment_reply(updated)
            return {
                "ok": True,
                "state": status,
                "already_fulfilled": already_fulfilled,
                "message": (
                    "Выполнение уже было подтверждено"
                    if already_fulfilled
                    else "Выполнение подтверждено на Playerok"
                ),
            }

    def _actor_fields(self, event: Any) -> tuple[str, str, str]:
        """Return display name, Playerok role and relation to the account owner.

        Playerok attaches the user that caused a deal-state marker to
        ``message.user``.  Older payload variants may expose a moderator or an
        event-side user instead, so keep conservative fallbacks.
        """
        message = _value(event, "message")
        actor = _value(message, "user")
        if actor is None:
            actor = _value(message, "moderator", "event_by_user", "eventByUser")
        if actor is None:
            actor = _value(message, "event_to_user", "eventToUser")

        actor_id = _text(_value(actor, "id"))
        name = _text(_value(actor, "username", "display_name", "displayName", "name"))
        raw_role = _value(actor, "role", "type")
        role = _text(getattr(raw_role, "name", raw_role)).upper()
        if "." in role:
            role = role.rsplit(".", 1)[-1]

        if actor_id and self.own_user_id and actor_id == self.own_user_id:
            relation = "SELF"
        elif role and role not in {"USER", "CUSTOMER"}:
            relation = "PLAYEROK"
        elif actor is not None:
            relation = "COUNTERPARTY"
        else:
            relation = ""
        return name, role, relation

    async def handle_item_paid(self, event: Any) -> None:
        deal_id, chat_id, item_name, price, buyer, buyer_comment, direction = self._extract_order(event)
        payment_message_id, payment_created_at = self._payment_fields(event)
        if not chat_id:
            log.error("ITEM_PAID without chat id; deal=%s", deal_id)
            return

        # Direction is authoritative: OUT = somebody paid our item/service,
        # IN = we paid another seller. Never auto-reply or emit a new-order alert
        # for our own purchases. If a lightweight chat message omitted direction,
        # refresh only this deal once.
        if direction not in {"IN", "OUT"}:
            try:
                fresh = await self.raw.get_deal(deal_id)
                event = SimpleNamespace(deal=fresh, chat=_value(event, "chat"), message=_value(event, "message"))
                deal_id, chat_id, item_name, price, buyer, buyer_comment, direction = self._extract_order(event)
            except Exception:
                log.exception("Could not determine deal direction deal=%s", deal_id)

        seller_net_amount, seller_net_status, seller_net_available_at = (
            self._seller_financial_fields(event)
        )

        async with self._locks[deal_id]:
            row = self.store.record(
                deal_id,
                chat_id,
                item_name,
                price,
                buyer,
                payment_message_id=payment_message_id,
                payment_created_at=payment_created_at,
                buyer_comment=buyer_comment,
                buyer_fields_json=self._buyer_fields_json(_value(event, "deal")),
                direction=direction,
                seller_net_amount=seller_net_amount,
                seller_net_status=seller_net_status,
                seller_net_available_at=seller_net_available_at,
            )
            deal = _value(event, "deal")
            self.persist_review(deal_id, deal, details_loaded=True)
            status = _enum_name(_value(deal, "status"))
            self.store.set_deal_progress(
                deal_id,
                deal_status=status or "PAID",
                seller_fulfilled=status in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"},
                recipient_confirmed=status in {"CONFIRMED", "CONFIRMED_AUTOMATICALLY"},
                recipient_at=_text(_value(deal, "completed_at", "completedAt")),
                recipient_automatic=status == "CONFIRMED_AUTOMATICALLY",
            )
            log.info(
                "ITEM_PAID deal=%s chat=%s direction=%s payment_message=%s",
                deal_id,
                chat_id,
                row.direction or "UNKNOWN",
                payment_message_id or "?",
            )
            if row.direction == "OUT":
                await self.bus.publish_order(
                    row.deal_id,
                    row.item_name,
                    row.price,
                    row.buyer,
                    seller_net_amount=row.seller_net_amount,
                    seller_net_status=row.seller_net_status,
                )
                await self.ensure_purchase_reply(row)

    async def handle_deal_progress(self, event: Any, marker: str) -> None:
        deal_id, chat_id, item_name, price, buyer, buyer_comment, direction = self._extract_order(event)
        seller_net_amount, seller_net_status, seller_net_available_at = self._seller_financial_fields(event)
        if not chat_id:
            log.error("Deal progress without chat id; deal=%s marker=%s", deal_id, marker)
            return

        message = _value(event, "message")
        message_id = _text(_value(message, "id"))
        event_at = _text(_value(message, "created_at", "createdAt"))
        actor_name, actor_role, actor_relation = self._actor_fields(event)
        deal = _value(event, "deal")
        status = _enum_name(_value(deal, "status"))
        is_seller = marker == ITEM_SENT_TEXT
        is_recipient = marker in {DEAL_CONFIRMED_TEXT, DEAL_CONFIRMED_AUTOMATICALLY_TEXT}
        automatic = marker == DEAL_CONFIRMED_AUTOMATICALLY_TEXT
        if is_seller and not status:
            status = "SENT"
        if is_recipient:
            status = "CONFIRMED_AUTOMATICALLY" if automatic else "CONFIRMED"

        async with self._locks[deal_id]:
            self.store.record(
                deal_id,
                chat_id,
                item_name,
                price,
                buyer,
                buyer_comment=buyer_comment,
                buyer_fields_json=self._buyer_fields_json(_value(event, "deal")),
                direction=direction,
                seller_net_amount=seller_net_amount,
                seller_net_status=seller_net_status,
                seller_net_available_at=seller_net_available_at,
            )
            self.persist_review(deal_id, deal, details_loaded=True)
            updated, changed = self.store.set_deal_progress(
                deal_id,
                deal_status=status,
                seller_fulfilled=is_seller or status in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"},
                seller_message_id=message_id if is_seller else "",
                seller_at=event_at if is_seller else "",
                recipient_confirmed=is_recipient or status in {"CONFIRMED", "CONFIRMED_AUTOMATICALLY"},
                recipient_message_id=message_id if is_recipient else "",
                recipient_at=event_at if is_recipient else _text(_value(deal, "completed_at", "completedAt")),
                recipient_automatic=automatic or status == "CONFIRMED_AUTOMATICALLY",
                actor_name=actor_name,
                actor_role=actor_role,
                actor_relation=actor_relation,
            )
            log.info(
                "%s deal=%s status=%s changed=%s",
                marker.strip("{}"),
                deal_id,
                status or "UNKNOWN",
                changed,
            )
            # ITEM_SENT in an OUT deal is the account owner's fulfillment.  The
            # same marker in an IN deal belongs to the other seller and must
            # never trigger our buyer message.  Do not require a false -> true
            # transition here: startup/backfill can persist SENT immediately
            # before this explicit chat marker is scanned.  Eligibility and the
            # attempted/sent journal inside ensure_fulfillment_reply keep old
            # orders and marker replays safe and idempotent.
            if (
                is_seller
                and updated is not None
                and updated.direction == "OUT"
                and updated.fulfillment_reply_eligible
                and not updated.fulfillment_reply_sent
                and not updated.rolled_back
            ):
                await self.ensure_fulfillment_reply(updated)

    async def handle_deal_problem(
        self,
        event: Any,
        *,
        active: bool,
        notify: bool = True,
    ) -> None:
        deal_id, chat_id, item_name, price, buyer, buyer_comment, direction = self._extract_order(event)
        seller_net_amount, seller_net_status, seller_net_available_at = self._seller_financial_fields(event)
        message = _value(event, "message")
        message_id = _text(_value(message, "id"))
        event_at = _text(_value(message, "created_at", "createdAt"))
        actor_name, actor_role, actor_relation = self._actor_fields(event)
        if not chat_id:
            log.error("Problem event without chat id; deal=%s", deal_id)
            return

        async with self._locks[deal_id]:
            # A problem can be discovered for a deal created before the monitor
            # was installed. Upsert the order first, using fresh deal/chat data.
            self.store.record(
                deal_id,
                chat_id,
                item_name,
                price,
                buyer,
                buyer_comment=buyer_comment,
                buyer_fields_json=self._buyer_fields_json(_value(event, "deal")),
                direction=direction,
                seller_net_amount=seller_net_amount,
                seller_net_status=seller_net_status,
                seller_net_available_at=seller_net_available_at,
            )
            row, changed = self.store.set_problem(
                deal_id,
                active=active,
                message_id=message_id,
                event_at=event_at,
                actor_name=actor_name,
                actor_role=actor_role,
                actor_relation=actor_relation,
            )
            if row is None:
                return

            marker = "DEAL_HAS_PROBLEM" if active else "DEAL_PROBLEM_RESOLVED"
            log.info(
                "%s deal=%s chat=%s message=%s changed=%s",
                marker,
                deal_id,
                chat_id,
                message_id or "?",
                changed,
            )
            # Message-scoped event keys make retries idempotent while still
            # allowing a later second problem on the same deal to alert again.
            if notify:
                await self.bus.publish_problem(
                    row,
                    message_id=message_id,
                    resolved=not active,
                )

    async def handle_deal_rolled_back(
        self,
        event: Any,
        *,
        notify: bool = True,
    ) -> None:
        deal_id, chat_id, item_name, price, buyer, buyer_comment, direction = self._extract_order(event)
        seller_net_amount, seller_net_status, seller_net_available_at = self._seller_financial_fields(event)
        message = _value(event, "message")
        message_id = _text(_value(message, "id"))
        event_at = _text(_value(message, "created_at", "createdAt"))
        actor_name, actor_role, actor_relation = self._actor_fields(event)
        if not chat_id:
            log.error("Rollback event without chat id; deal=%s", deal_id)
            return

        async with self._locks[deal_id]:
            self.store.record(
                deal_id,
                chat_id,
                item_name,
                price,
                buyer,
                buyer_comment=buyer_comment,
                buyer_fields_json=self._buyer_fields_json(_value(event, "deal")),
                direction=direction,
                seller_net_amount=seller_net_amount,
                seller_net_status=seller_net_status,
                seller_net_available_at=seller_net_available_at,
            )
            row, changed = self.store.set_rolled_back(
                deal_id,
                message_id=message_id,
                event_at=event_at,
                actor_name=actor_name,
                actor_role=actor_role,
                actor_relation=actor_relation,
            )
            if row is None:
                return
            log.info(
                "DEAL_ROLLED_BACK deal=%s chat=%s message=%s changed=%s actor=%s",
                deal_id,
                chat_id,
                message_id or "?",
                changed,
                actor_relation or "UNKNOWN",
            )
            if notify:
                await self.bus.publish_rollback(row, message_id=message_id)

    async def ensure_purchase_reply(self, row: OrderRow) -> None:
        """Choose the paid-order reply path once, then resume it safely.

        The selected mode is persisted before any Playerok write.  This makes
        retries independent from later schedule edits and ensures an order can
        never receive both the sleep notice and the ordinary reply at payment
        time.
        """
        cur = self.store.get(row.deal_id) or row
        if cur.direction != "OUT" or cur.reply_sent or not cur.sleep_reply_eligible:
            return

        if not cur.reply_mode:
            config = self.store.get_auto_reply_config(
                self.settings.auto_reply_enabled,
                [self.settings.auto_reply_text],
            )
            paid_at = (
                _parse_dt(cur.payment_created_at)
                or _parse_dt(cur.first_seen_at)
                or datetime.now(timezone.utc)
            )
            mode = "SLEEP" if config.sleep_active_at(paid_at) else "NORMAL"
            cur = self.store.set_reply_mode_if_empty(cur.deal_id, mode) or cur

        if cur.reply_mode == "SLEEP":
            await self.ensure_sleep_reply(cur)
        else:
            await self.ensure_auto_reply(cur)

    async def ensure_auto_reply(self, row: OrderRow) -> None:
        cur = self.store.get(row.deal_id) or row
        if cur.direction != "OUT":
            return
        if cur.reply_sent:
            return
        # Sleep orders deliberately defer the ordinary paid-order sequence
        # until the owner explicitly presses "Я проснулся" in the app.
        if cur.reply_mode == "SLEEP" and not cur.wake_reply_requested:
            return
        # Never send the initial "please wait" message after the seller has
        # already fulfilled the order, after receipt/rollback, or while replaying
        # an old database row during a service restart.
        finished = (
            cur.seller_fulfilled
            or cur.recipient_confirmed
            or cur.rolled_back
            or cur.deal_status in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY", "ROLLED_BACK"}
        )
        paid_at = _parse_dt(cur.payment_created_at) or _parse_dt(cur.first_seen_at)
        stale = bool(
            paid_at
            and not cur.wake_reply_requested
            and (datetime.now(timezone.utc) - paid_at).total_seconds() > 30 * 60
        )
        if finished or stale:
            self.store.set_reply_sent(cur.deal_id)
            log.info(
                "Auto-reply suppressed deal=%s finished=%s stale=%s status=%s",
                cur.deal_id,
                finished,
                stale,
                cur.deal_status or "UNKNOWN",
            )
            return
        config = self.store.get_auto_reply_config(
            self.settings.auto_reply_enabled,
            [self.settings.auto_reply_text],
        )
        if not config.enabled:
            # Orders first seen while replies are disabled are intentionally
            # closed, not queued. Re-enabling must never unleash a backlog.
            if not cur.reply_attempted:
                self.store.set_reply_sent(row.deal_id)
                log.info("Auto-reply disabled; order suppressed deal=%s", cur.deal_id)
            return

        try:
            if not cur.reply_attempted:
                messages = config.messages
                self.store.set_reply_attempted(cur.deal_id, messages)
                cur = self.store.get(cur.deal_id) or cur
            else:
                try:
                    decoded = json.loads(cur.reply_messages_json) if cur.reply_messages_json else []
                    messages = tuple(
                        message.strip()
                        for message in decoded
                        if isinstance(message, str) and message.strip()
                    )
                except (TypeError, json.JSONDecodeError):
                    messages = ()
                # Migrated attempts made by an older server have no snapshot.
                # Pin them to the historical text, never to a newly edited list.
                if not messages:
                    messages = (self.settings.auto_reply_text,)

            sent_id = cur.reply_message_id
            for index, message in enumerate(messages):
                latest_config = self.store.get_auto_reply_config(
                    self.settings.auto_reply_enabled,
                    [self.settings.auto_reply_text],
                )
                if not latest_config.enabled:
                    log.info(
                        "Auto-reply sequence paused deal=%s next=%s/%s",
                        cur.deal_id,
                        index + 1,
                        len(messages),
                    )
                    return
                if await self._reply_already_in_chat(cur, message):
                    log.info(
                        "Auto-reply message already exists deal=%s part=%s/%s",
                        cur.deal_id,
                        index + 1,
                        len(messages),
                    )
                    continue
                sent = await self.raw.send_message(
                    chat_id=cur.chat_id,
                    text=message,
                    mark_chat_as_read=False,
                )
                sent_id = _text(_value(sent, "id")) or sent_id
                if index + 1 < len(messages):
                    await asyncio.sleep(0.8)
            self.store.set_reply_sent(cur.deal_id, sent_id)
            log.info(
                "Auto-reply sequence complete deal=%s parts=%s message=%s",
                cur.deal_id,
                len(messages),
                sent_id or "?",
            )
        except Exception as exc:
            self.store.set_error(cur.deal_id, f"{type(exc).__name__}: {exc}")
            log.exception("Auto-reply failed deal=%s", cur.deal_id)

    async def ensure_sleep_reply(self, row: OrderRow) -> None:
        """Send the pinned sleep notice for a newly observed sale exactly once."""
        cur = self.store.get(row.deal_id) or row
        if (
            cur.direction != "OUT"
            or not cur.sleep_reply_eligible
            or cur.reply_mode != "SLEEP"
            or cur.sleep_reply_sent
            or cur.reply_sent
        ):
            return

        finished = (
            cur.seller_fulfilled
            or cur.recipient_confirmed
            or cur.rolled_back
            or cur.deal_status
            in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY", "ROLLED_BACK"}
        )
        paid_at = _parse_dt(cur.payment_created_at) or _parse_dt(cur.first_seen_at)
        stale = bool(
            paid_at
            and (datetime.now(timezone.utc) - paid_at).total_seconds() > 30 * 60
        )
        if finished or stale:
            # Close both stages.  A delayed watcher replay must never create a
            # sleep notice or a future wake button for an old/finished order.
            self.store.set_reply_sent(cur.deal_id)
            log.info(
                "Sleep reply suppressed deal=%s finished=%s stale=%s status=%s",
                cur.deal_id,
                finished,
                stale,
                cur.deal_status or "UNKNOWN",
            )
            return

        config = self.store.get_auto_reply_config(
            self.settings.auto_reply_enabled,
            [self.settings.auto_reply_text],
        )
        if not config.enabled:
            self.store.set_reply_sent(cur.deal_id)
            log.info("Sleep reply disabled; order suppressed deal=%s", cur.deal_id)
            return

        try:
            if not cur.sleep_reply_attempted:
                message = config.sleep_message
                self.store.set_sleep_reply_attempted(cur.deal_id, message)
                cur = self.store.get(cur.deal_id) or cur
            else:
                message = cur.sleep_reply_text.strip() or config.sleep_message

            latest_config = self.store.get_auto_reply_config(
                self.settings.auto_reply_enabled,
                [self.settings.auto_reply_text],
            )
            if not latest_config.enabled:
                self.store.set_reply_sent(cur.deal_id)
                log.info("Sleep reply cancelled while disabled deal=%s", cur.deal_id)
                return
            if await self._reply_already_in_chat(cur, message):
                self.store.set_sleep_reply_sent(cur.deal_id)
                log.info("Sleep reply already exists deal=%s", cur.deal_id)
                return

            sent = await self.raw.send_message(
                chat_id=cur.chat_id,
                text=message,
                mark_chat_as_read=False,
            )
            sent_id = _text(_value(sent, "id"))
            self.store.set_sleep_reply_sent(cur.deal_id, sent_id)
            log.info(
                "Sleep reply complete deal=%s message=%s",
                cur.deal_id,
                sent_id or "?",
            )
        except Exception as exc:
            self.store.set_error(cur.deal_id, f"{type(exc).__name__}: {exc}")
            log.exception("Sleep reply failed deal=%s", cur.deal_id)

    async def request_wake_reply(self, deal_id: str) -> dict[str, object]:
        """Send the ordinary paid-order sequence after an explicit wake action."""
        async with self._locks[deal_id]:
            cur = self.store.get(deal_id)
            if cur is None:
                return {
                    "ok": False,
                    "code": "ORDER_NOT_FOUND",
                    "message": "Заказ не найден",
                }
            if cur.direction != "OUT" or cur.reply_mode != "SLEEP":
                return {
                    "ok": False,
                    "code": "WAKE_NOT_AVAILABLE",
                    "message": "Для этого заказа действие недоступно",
                }
            if not cur.sleep_reply_sent:
                return {
                    "ok": False,
                    "code": "SLEEP_REPLY_NOT_SENT",
                    "message": "Покупателю не отправлялось сообщение о сне",
                }
            if cur.reply_sent:
                return {
                    "ok": True,
                    "already_sent": True,
                    "message": "Сообщение о пробуждении уже отправлено",
                }

            finished = (
                cur.seller_fulfilled
                or cur.recipient_confirmed
                or cur.rolled_back
                or cur.deal_status
                in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY", "ROLLED_BACK"}
            )
            if finished:
                return {
                    "ok": False,
                    "code": "ORDER_FINISHED",
                    "message": "Заказ уже выполнен или завершён",
                }

            config = self.store.get_auto_reply_config(
                self.settings.auto_reply_enabled,
                [self.settings.auto_reply_text],
            )
            if not config.enabled:
                return {
                    "ok": False,
                    "code": "MESSAGES_DISABLED",
                    "message": "Сначала включите отправку сообщений в настройках",
                }

            cur = self.store.set_wake_reply_requested(deal_id) or cur
            await self.ensure_auto_reply(cur)
            latest = self.store.get(deal_id) or cur
            if latest.reply_sent:
                return {
                    "ok": True,
                    "already_sent": bool(cur.reply_sent),
                    "message": "Покупателю отправлено обычное сообщение по заказу",
                }
            return {
                "ok": False,
                "code": "SEND_FAILED",
                "message": latest.last_error or "Не удалось отправить сообщение. Попробуйте ещё раз",
            }

    async def ensure_fulfillment_reply(self, row: OrderRow) -> None:
        """Send the message tied to our own fulfillment exactly once.

        Eligibility is a migration boundary, direction identifies whose sale it
        is, and attempted/sent fields form an idempotent retry journal.  The
        chosen text is pinned before the network call so an editor change can
        never alter an in-flight retry.
        """
        cur = self.store.get(row.deal_id) or row
        if (
            cur.direction != "OUT"
            or not cur.fulfillment_reply_eligible
            or not cur.seller_fulfilled
            or cur.rolled_back
            or cur.fulfillment_reply_sent
        ):
            return

        # Once receipt is already confirmed, asking for confirmation is stale.
        if cur.recipient_confirmed:
            self.store.set_fulfillment_reply_sent(cur.deal_id)
            log.info("Fulfillment reply suppressed after receipt deal=%s", cur.deal_id)
            return

        config = self.store.get_auto_reply_config(
            self.settings.auto_reply_enabled,
            [self.settings.auto_reply_text],
        )
        if not config.enabled:
            # A disabled interval is not a queue. Re-enabling messages later
            # must not send fulfillment replies for actions made while off.
            self.store.set_fulfillment_reply_sent(cur.deal_id)
            log.info("Fulfillment reply disabled; order suppressed deal=%s", cur.deal_id)
            return

        try:
            if not cur.fulfillment_reply_attempted:
                message = config.fulfillment_message
                self.store.set_fulfillment_reply_attempted(cur.deal_id, message)
                cur = self.store.get(cur.deal_id) or cur
            else:
                message = cur.fulfillment_reply_text.strip()
                if not message:
                    # Compatibility for an interrupted migration between the
                    # attempt flag and text snapshot.
                    message = config.fulfillment_message

            latest_config = self.store.get_auto_reply_config(
                self.settings.auto_reply_enabled,
                [self.settings.auto_reply_text],
            )
            if not latest_config.enabled:
                self.store.set_fulfillment_reply_sent(cur.deal_id)
                log.info("Fulfillment reply cancelled while disabled deal=%s", cur.deal_id)
                return
            if await self._fulfillment_reply_already_in_chat(cur, message):
                self.store.set_fulfillment_reply_sent(cur.deal_id)
                log.info("Fulfillment reply already exists deal=%s", cur.deal_id)
                return

            sent = await self.raw.send_message(
                chat_id=cur.chat_id,
                text=message,
                mark_chat_as_read=False,
            )
            sent_id = _text(_value(sent, "id"))
            self.store.set_fulfillment_reply_sent(cur.deal_id, sent_id)
            log.info(
                "Fulfillment reply complete deal=%s message=%s",
                cur.deal_id,
                sent_id or "?",
            )
        except Exception as exc:
            self.store.set_error(cur.deal_id, f"{type(exc).__name__}: {exc}")
            log.exception("Fulfillment reply failed deal=%s", cur.deal_id)

    async def _fulfillment_reply_already_in_chat(
        self,
        row: OrderRow,
        text: str,
    ) -> bool:
        """Detect our exact text only after this order's ITEM_SENT marker."""
        try:
            page = await self.raw.get_chat_messages(chat_id=row.chat_id, count=24)
            messages = list(getattr(page, "messages", []) or [])
            messages.sort(
                key=lambda m: _parse_dt(_value(m, "created_at", "createdAt"))
                or datetime.min.replace(tzinfo=timezone.utc)
            )

            start_index: int | None = None
            for idx, msg in enumerate(messages):
                if (
                    row.seller_fulfilled_message_id
                    and _text(_value(msg, "id")) == row.seller_fulfilled_message_id
                ):
                    start_index = idx
                    break

            if start_index is None and row.seller_fulfilled_at:
                sent_dt = _parse_dt(row.seller_fulfilled_at)
                if sent_dt is not None:
                    for idx, msg in enumerate(messages):
                        msg_dt = _parse_dt(_value(msg, "created_at", "createdAt"))
                        if msg_dt is not None and msg_dt >= sent_dt:
                            start_index = max(0, idx - 1)
                            break

            if start_index is None:
                return False

            for msg in messages[start_index + 1 :]:
                if _text(_value(msg, "text")) == ITEM_PAID_TEXT:
                    break
                if _text(_value(msg, "text")) != text:
                    continue
                sender = _value(msg, "user")
                sender_id = _text(_value(sender, "id"))
                if not sender_id or not self.own_user_id or sender_id == self.own_user_id:
                    return True
            return False
        except Exception:
            log.exception(
                "Could not verify fulfillment reply deal=%s chat=%s",
                row.deal_id,
                row.chat_id,
            )
            return False

    async def _reply_already_in_chat(self, row: OrderRow, text: str) -> bool:
        """Check the reply interval belonging to this specific order.

        A single Playerok chat may contain payment #1, reply #1, payment #2,
        reply #2, ... . Looking for the text anywhere in the chat would make
        payment #2 incorrectly inherit reply #1.
        """
        try:
            page = await self.raw.get_chat_messages(chat_id=row.chat_id, count=24)
            messages = list(getattr(page, "messages", []) or [])
            messages.sort(
                key=lambda m: _parse_dt(_value(m, "created_at"))
                or datetime.min.replace(tzinfo=timezone.utc)
            )

            if not row.payment_message_id and not row.payment_created_at:
                return any(
                    _text(_value(msg, "text")) == text
                    for msg in messages
                )

            start_index: int | None = None
            if row.wake_reply_requested and row.sleep_reply_sent:
                for idx, msg in enumerate(messages):
                    if (
                        row.sleep_reply_message_id
                        and _text(_value(msg, "id")) == row.sleep_reply_message_id
                    ):
                        start_index = idx
                        break
                if start_index is None and row.wake_reply_requested_at:
                    wake_dt = _parse_dt(row.wake_reply_requested_at)
                    if wake_dt is not None:
                        for idx, msg in enumerate(messages):
                            msg_dt = _parse_dt(_value(msg, "created_at"))
                            if msg_dt is not None and msg_dt >= wake_dt:
                                start_index = max(0, idx - 1)
                                break
            for idx, msg in enumerate(messages):
                if start_index is not None:
                    break
                if row.payment_message_id and _text(_value(msg, "id")) == row.payment_message_id:
                    start_index = idx
                    break

            if start_index is None and row.payment_created_at:
                paid_dt = _parse_dt(row.payment_created_at)
                if paid_dt is not None:
                    for idx, msg in enumerate(messages):
                        msg_dt = _parse_dt(_value(msg, "created_at"))
                        if msg_dt is not None and msg_dt >= paid_dt:
                            start_index = max(0, idx - 1)
                            break

            if start_index is None:
                return False

            end_index = len(messages)
            for idx in range(start_index + 1, len(messages)):
                if _text(_value(messages[idx], "text")) == ITEM_PAID_TEXT:
                    end_index = idx
                    break

            for msg in messages[start_index + 1 : end_index]:
                if _text(_value(msg, "text")) != text:
                    continue
                sender = _value(msg, "user")
                sender_id = _text(_value(sender, "id"))
                if not sender_id or not self.own_user_id or sender_id == self.own_user_id:
                    return True
            return False
        except Exception:
            log.exception(
                "Could not verify per-order chat history deal=%s chat=%s",
                row.deal_id,
                row.chat_id,
            )
            return False

    async def retry_pending_forever(self) -> None:
        while True:
            await asyncio.sleep(self.settings.retry_interval_seconds)
            for row in self.store.pending_sleep_replies():
                async with self._locks[row.deal_id]:
                    await self.ensure_sleep_reply(row)
            for row in self.store.pending_replies():
                async with self._locks[row.deal_id]:
                    await self.ensure_auto_reply(row)
            for row in self.store.pending_fulfillment_replies():
                async with self._locks[row.deal_id]:
                    await self.ensure_fulfillment_reply(row)
