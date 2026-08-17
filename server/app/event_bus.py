from __future__ import annotations

import asyncio
import hmac
import json
import logging
from urllib.parse import parse_qs, urlsplit

from .auto_reply import (
    DEFAULT_AUTO_REPLY_TEXT,
    DEFAULT_FULFILLMENT_REPLY_TEXT,
    DEFAULT_SLEEP_REPLY_TEXT,
)
from .db import EventRow, OrderRow, OrderStore
from .relist import RelistError, RelistService

log = logging.getLogger(__name__)


def _safe(text: str) -> str:
    return " ".join((text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").split())


def _money(text: str) -> str:
    value = _safe(text)
    if not value or "₽" in value or "руб" in value.lower():
        return value
    return f"{value.replace('.', ',')} ₽"


def _order_json(row: OrderRow) -> dict[str, object]:
    wake_finished = (
        row.seller_fulfilled
        or row.recipient_confirmed
        or row.rolled_back
        or row.deal_status in {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY", "ROLLED_BACK"}
    )
    try:
        buyer_fields = json.loads(row.buyer_fields_json or "[]")
        if not isinstance(buyer_fields, list):
            buyer_fields = []
    except (TypeError, ValueError, json.JSONDecodeError):
        buyer_fields = []
    return {
        "deal_id": row.deal_id,
        "chat_id": row.chat_id,
        "direction": row.direction,
        "item_name": row.item_name,
        "price": row.price,
        "seller_net_amount": row.seller_net_amount,
        "seller_net_status": row.seller_net_status,
        "seller_net_available_at": row.seller_net_available_at,
        "buyer": row.buyer,
        "counterparty": row.buyer,
        "buyer_comment": row.buyer_comment,
        "buyer_fields": buyer_fields,
        "paid_at": row.payment_created_at or row.first_seen_at,
        "problem_active": row.problem_active,
        "problem_reported_at": row.problem_reported_at,
        "problem_resolved_at": row.problem_resolved_at,
        "problem_reported_by_name": row.problem_reported_by_name,
        "problem_reported_by_role": row.problem_reported_by_role,
        "problem_reported_by_relation": row.problem_reported_by_relation,
        "problem_resolved_by_name": row.problem_resolved_by_name,
        "problem_resolved_by_role": row.problem_resolved_by_role,
        "problem_resolved_by_relation": row.problem_resolved_by_relation,
        "rolled_back": row.rolled_back,
        "rolled_back_at": row.rolled_back_at,
        "rolled_back_by_name": row.rolled_back_by_name,
        "rolled_back_by_role": row.rolled_back_by_role,
        "rolled_back_by_relation": row.rolled_back_by_relation,
        "deal_status": row.deal_status,
        "seller_fulfilled": row.seller_fulfilled,
        "seller_fulfilled_at": row.seller_fulfilled_at,
        "seller_fulfilled_by_name": row.seller_fulfilled_by_name,
        "seller_fulfilled_by_role": row.seller_fulfilled_by_role,
        "seller_fulfilled_by_relation": row.seller_fulfilled_by_relation,
        "recipient_confirmed": row.recipient_confirmed,
        "recipient_confirmed_at": row.recipient_confirmed_at,
        "recipient_confirmation_automatic": row.recipient_confirmation_automatic,
        "recipient_confirmed_by_name": row.recipient_confirmed_by_name,
        "recipient_confirmed_by_role": row.recipient_confirmed_by_role,
        "recipient_confirmed_by_relation": row.recipient_confirmed_by_relation,
        "review_rating": row.review_rating,
        "review_text": row.review_text,
        "review_created_at": row.review_created_at,
        "review_author": row.review_author,
        "relist_eligible": row.relist_eligible,
        "relist_state": row.relist_state,
        "relist_draft_item_id": row.relist_draft_item_id,
        "relisted_item_id": row.relisted_item_id,
        "relisted_item_url": (
            f"https://playerok.com/products/{row.relisted_item_slug}"
            if row.relisted_item_slug
            else ""
        ),
        "relist_priority_price": row.relist_priority_price,
        "relist_priority_type": row.relist_priority_type,
        "relist_listing_price": row.relist_listing_price,
        "relisted_at": row.relisted_at,
        "relist_error": row.relist_error,
        "reply_sent": row.reply_sent,
        "reply_mode": row.reply_mode,
        "sleep_reply_sent": row.sleep_reply_sent,
        "wake_reply_requested": row.wake_reply_requested,
        "wake_reply_available": bool(
            row.direction == "OUT"
            and row.reply_mode == "SLEEP"
            and row.sleep_reply_sent
            and not row.reply_sent
            and not wake_finished
        ),
        "wake_reply_sent": bool(row.sleep_reply_sent and row.reply_sent),
        "revision": row.revision,
        "deal_url": f"https://playerok.com/deal/{row.deal_id}",
    }


class EventBus:
    def __init__(self, store: OrderStore, api_token: str) -> None:
        self.store = store
        self.api_token = api_token
        self._condition = asyncio.Condition()

    async def _notify(self, row: EventRow, created: bool) -> EventRow:
        if created:
            async with self._condition:
                self._condition.notify_all()
            log.info(
                "Android event queued id=%s kind=%s deal=%s",
                row.id,
                row.kind,
                row.deal_id,
            )
        return row

    async def publish_order(
        self,
        deal_id: str,
        item_name: str,
        price: str,
        buyer: str,
        *,
        seller_net_amount: str = "",
        seller_net_status: str = "",
    ) -> EventRow:
        clean_status = (seller_net_status or "").strip().upper()
        net_label = {
            "PENDING": "ожидается",
            "PROCESSING": "в заморозке",
            "CONFIRMED": "зачислено",
        }.get(clean_status, "к получению")
        price_text = _safe(price)
        if seller_net_amount and clean_status not in {"ROLLED_BACK", "FAILED"}:
            price_text = f"{price_text} ({net_label}: {_money(seller_net_amount)})"
        details = [
            x
            for x in (
                _safe(item_name),
                price_text,
                f"Покупатель: {_safe(buyer)}" if buyer else "",
            )
            if x
        ]
        body = " • ".join(details) if details else f"Сделка {deal_id} оплачена"
        row, created = self.store.add_event(
            deal_id,
            deal_id,
            "ORDER_PAID",
            "Новый заказ Playerok",
            body,
        )
        return await self._notify(row, created)

    async def publish_auto_relist(
        self,
        order: OrderRow,
        *,
        payment_id: str,
        priority_price: int,
    ) -> EventRow:
        fee = max(0, int(priority_price))
        placement = f"Premium: {fee} ₽" if fee else "Размещение: бесплатно"
        details = [x for x in (_safe(order.item_name), placement) if x]
        row, created = self.store.add_event(
            f"auto-relist:{order.deal_id}:{payment_id}",
            order.deal_id,
            "ITEM_AUTO_RELISTED",
            "Товар автоматически перевыставлен",
            " • ".join(details),
        )
        return await self._notify(row, created)

    async def publish_problem(
        self,
        order: OrderRow,
        *,
        message_id: str,
        resolved: bool,
    ) -> EventRow:
        is_sale = order.direction == "OUT"
        if resolved:
            kind = "PROBLEM_RESOLVED"
            title = "Проблема по продаже решена" if is_sale else "Проблема по покупке решена"
            body = _safe(order.item_name) or f"Сделка {order.deal_id}"
            prefix = "problem-resolved"
        else:
            kind = "PROBLEM_CREATED"
            title = "Проблема по моей продаже" if is_sale else "Проблема по моей покупке"
            counterparty_label = "Покупатель" if is_sale else "Продавец"
            details = [
                x
                for x in (
                    _safe(order.item_name),
                    _safe(order.price),
                    f"{counterparty_label}: {_safe(order.buyer)}" if order.buyer else "",
                    "Требует быстрой реакции",
                )
                if x
            ]
            body = " • ".join(details)
            prefix = "problem"
        suffix = message_id or (order.problem_reported_at if not resolved else order.problem_resolved_at) or "state"
        event_key = f"{prefix}:{order.deal_id}:{suffix}"
        row, created = self.store.add_event(
            event_key,
            order.deal_id,
            kind,
            title,
            body,
        )
        return await self._notify(row, created)

    async def publish_rollback(
        self,
        order: OrderRow,
        *,
        message_id: str,
    ) -> EventRow:
        is_sale = order.direction == "OUT"
        title = "Возврат по моей продаже" if is_sale else "Возврат по моей покупке"
        actor = self._actor_label(
            order.rolled_back_by_name,
            order.rolled_back_by_role,
            order.rolled_back_by_relation,
            is_sale,
        )
        details = [
            x
            for x in (
                _safe(order.item_name),
                _safe(order.price),
                f"Выполнил: {actor}" if actor else "",
            )
            if x
        ]
        suffix = message_id or order.rolled_back_at or "state"
        row, created = self.store.add_event(
            f"rollback:{order.deal_id}:{suffix}",
            order.deal_id,
            "DEAL_ROLLED_BACK",
            title,
            " • ".join(details) or f"Сделка {order.deal_id}",
        )
        return await self._notify(row, created)

    @staticmethod
    def _actor_label(name: str, role: str, relation: str, is_sale: bool) -> str:
        if relation == "SELF":
            return "Вы"
        if relation == "PLAYEROK":
            suffix = name or role
            return f"Playerok · {suffix}" if suffix else "Playerok"
        if relation == "COUNTERPARTY":
            party = "Покупатель" if is_sale else "Продавец"
            return f"{party} · {name}" if name else party
        return name or role

    async def wait_next(self, after: int, timeout: float = 45.0) -> EventRow | None:
        row = self.store.next_event(after)
        if row is not None:
            return row
        try:
            async with self._condition:
                await asyncio.wait_for(self._condition.wait(), timeout=timeout)
        except TimeoutError:
            return None
        return self.store.next_event(after)

    def authorized(self, token: str) -> bool:
        return hmac.compare_digest(token or "", self.api_token)


class PollServer:
    def __init__(
        self,
        bus: EventBus,
        host: str,
        port: int,
        relist_service: RelistService | None = None,
        default_auto_reply_enabled: bool = True,
        default_auto_reply_text: str = DEFAULT_AUTO_REPLY_TEXT,
        default_fulfillment_reply_text: str = DEFAULT_FULFILLMENT_REPLY_TEXT,
    ) -> None:
        self.bus, self.host, self.port = bus, host, port
        self.relist_service = relist_service
        self.default_auto_reply_enabled = default_auto_reply_enabled
        self.default_auto_reply_text = default_auto_reply_text
        self.default_fulfillment_reply_text = default_fulfillment_reply_text
        self.order_processor = None
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port, limit=8192)
        sockets = self._server.sockets or []
        log.info("Android poll server listening: %s", ", ".join(str(s.getsockname()) for s in sockets))

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @staticmethod
    async def _response(
        writer: asyncio.StreamWriter,
        status: str,
        body: str,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        data = body.encode("utf-8")
        head = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(data)}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(head + data)
        await writer.drain()

    @classmethod
    async def _json_response(
        cls,
        writer: asyncio.StreamWriter,
        status: str,
        payload: dict[str, object],
    ) -> None:
        await cls._response(
            writer,
            status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "application/json; charset=utf-8",
        )

    async def _relist_response(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        q: dict[str, list[str]],
    ) -> None:
        if self.relist_service is None:
            await self._json_response(
                writer,
                "503 Service Unavailable",
                {"ok": False, "code": "NOT_READY", "message": "Playerok ещё подключается"},
            )
            return
        deal_id = q.get("deal_id", [""])[0]
        try:
            if method == "GET":
                setup_only = q.get("setup", [""])[0] == "1"
                listing_price_raw = q.get("listing_price", [""])[0]
                try:
                    listing_price = int(listing_price_raw) if listing_price_raw else None
                except ValueError:
                    raise RelistError(
                        "INVALID_LISTING_PRICE",
                        "Укажите целую цену товара в рублях",
                    )
                payload = await self.relist_service.preview(
                    deal_id,
                    listing_price=listing_price,
                    priority_type=(
                        None
                        if setup_only
                        else q.get("priority_type", ["PREMIUM"])[0]
                    ),
                )
            elif method == "POST":
                priority_id = q.get("priority_id", [""])[0]
                try:
                    priority_price = int(q.get("priority_price", ["-1"])[0])
                except ValueError:
                    priority_price = -1
                listing_price_raw = q.get("listing_price", [""])[0]
                try:
                    listing_price = int(listing_price_raw) if listing_price_raw else None
                except ValueError:
                    raise RelistError(
                        "INVALID_LISTING_PRICE",
                        "Укажите целую цену товара в рублях",
                    )
                if not priority_id or priority_price < 0:
                    raise RelistError(
                        "CONFIRMATION_REQUIRED",
                        "Сначала получите и подтвердите актуальные условия публикации",
                    )
                payload = await self.relist_service.execute(
                    deal_id,
                    confirmed_priority_id=priority_id,
                    confirmed_price=priority_price,
                    listing_price=listing_price,
                    priority_type=q.get("priority_type", ["PREMIUM"])[0],
                )
            else:
                await self._json_response(
                    writer,
                    "405 Method Not Allowed",
                    {"ok": False, "code": "METHOD_NOT_ALLOWED", "message": "Метод не поддерживается"},
                )
                return
            await self._json_response(writer, "200 OK", payload)
        except RelistError as exc:
            statuses = {
                400: "400 Bad Request",
                403: "403 Forbidden",
                404: "404 Not Found",
                409: "409 Conflict",
                429: "429 Too Many Requests",
                502: "502 Bad Gateway",
                503: "503 Service Unavailable",
            }
            await self._json_response(
                writer,
                statuses.get(exc.http_status, "400 Bad Request"),
                {"ok": False, "code": exc.code, "message": exc.message},
            )

    async def _orders_response(
        self,
        writer: asyncio.StreamWriter,
        q: dict[str, list[str]],
    ) -> None:
        try:
            after_rev = max(0, int(q.get("after_rev", ["0"])[0]))
        except ValueError:
            after_rev = 0
        try:
            limit = max(1, min(200, int(q.get("limit", ["100"])[0])))
        except ValueError:
            limit = 100

        revision = self.bus.store.current_revision()
        if after_rev >= revision:
            payload = {"revision": revision, "unchanged": True, "orders": []}
        else:
            payload = {
                "revision": revision,
                "unchanged": False,
                "orders": [_order_json(row) for row in self.bus.store.list_orders(limit)],
            }
        await self._response(
            writer,
            "200 OK",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "application/json; charset=utf-8",
        )

    async def _auto_replies_response(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        body: bytes,
    ) -> None:
        current = self.bus.store.get_auto_reply_config(
            self.default_auto_reply_enabled,
            [self.default_auto_reply_text],
            self.default_fulfillment_reply_text,
        )
        if method == "GET":
            await self._json_response(
                writer,
                "200 OK",
                current.payload(
                    self.default_auto_reply_text,
                    self.default_fulfillment_reply_text,
                ),
            )
            return
        if method != "POST":
            await self._json_response(
                writer,
                "405 Method Not Allowed",
                {"ok": False, "code": "METHOD_NOT_ALLOWED", "message": "Метод не поддерживается"},
            )
            return

        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Ожидался JSON-объект")
            enabled = payload.get("enabled", current.enabled)
            if not isinstance(enabled, bool):
                raise ValueError("Поле enabled должно быть true или false")
            messages = payload.get("messages", list(current.messages))
            if not isinstance(messages, list):
                raise ValueError("Поле messages должно быть списком")
            fulfillment_message = payload.get(
                "fulfillment_message", current.fulfillment_message
            )
            if not isinstance(fulfillment_message, str):
                raise ValueError("Поле fulfillment_message должно быть текстом")
            sleep_enabled = payload.get("sleep_enabled", current.sleep_enabled)
            if not isinstance(sleep_enabled, bool):
                raise ValueError("Поле sleep_enabled должно быть true или false")
            sleep_start = payload.get("sleep_start", current.sleep_start)
            sleep_end = payload.get("sleep_end", current.sleep_end)
            sleep_timezone = payload.get("sleep_timezone", current.sleep_timezone)
            sleep_message = payload.get("sleep_message", current.sleep_message)
            if not all(isinstance(value, str) for value in (
                sleep_start, sleep_end, sleep_timezone, sleep_message
            )):
                raise ValueError("Параметры периода сна должны быть текстом")
            saved = self.bus.store.set_auto_reply_config(
                enabled=enabled,
                messages=messages,
                fallback=self.default_auto_reply_text,
                fulfillment_message=fulfillment_message,
                fulfillment_fallback=self.default_fulfillment_reply_text,
                sleep_enabled=sleep_enabled,
                sleep_start=sleep_start,
                sleep_end=sleep_end,
                sleep_timezone=sleep_timezone,
                sleep_message=sleep_message,
                sleep_fallback=DEFAULT_SLEEP_REPLY_TEXT,
            )
            log.info(
                "Auto-reply settings updated enabled=%s messages=%s revision=%s",
                saved.enabled,
                len(saved.messages),
                saved.revision,
            )
            await self._json_response(
                writer,
                "200 OK",
                saved.payload(
                    self.default_auto_reply_text,
                    self.default_fulfillment_reply_text,
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            await self._json_response(
                writer,
                "400 Bad Request",
                {"ok": False, "code": "INVALID_AUTO_REPLY_SETTINGS", "message": str(exc)},
            )

    async def _wake_response(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        q: dict[str, list[str]],
    ) -> None:
        if method != "POST":
            await self._json_response(
                writer,
                "405 Method Not Allowed",
                {"ok": False, "code": "METHOD_NOT_ALLOWED", "message": "Нужен POST-запрос"},
            )
            return
        deal_id = (q.get("deal_id", [""])[0] or "").strip()
        if not deal_id:
            await self._json_response(
                writer,
                "400 Bad Request",
                {"ok": False, "code": "DEAL_REQUIRED", "message": "Не указан заказ"},
            )
            return
        if self.order_processor is None:
            await self._json_response(
                writer,
                "503 Service Unavailable",
                {"ok": False, "code": "NOT_READY", "message": "Монитор ещё запускается"},
            )
            return
        result = await self.order_processor.request_wake_reply(deal_id)
        status = "200 OK" if bool(result.get("ok")) else "409 Conflict"
        await self._json_response(writer, status, result)

    async def _fulfill_response(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        q: dict[str, list[str]],
    ) -> None:
        if method != "POST":
            await self._json_response(
                writer,
                "405 Method Not Allowed",
                {"ok": False, "code": "METHOD_NOT_ALLOWED", "message": "Нужен POST-запрос"},
            )
            return
        deal_id = (q.get("deal_id", [""])[0] or "").strip()
        if not deal_id:
            await self._json_response(
                writer,
                "400 Bad Request",
                {"ok": False, "code": "DEAL_REQUIRED", "message": "Не указан заказ"},
            )
            return
        if self.order_processor is None:
            await self._json_response(
                writer,
                "503 Service Unavailable",
                {"ok": False, "code": "NOT_READY", "message": "Монитор ещё запускается"},
            )
            return
        result = await self.order_processor.request_fulfillment(deal_id)
        status = "200 OK" if bool(result.get("ok")) else "409 Conflict"
        await self._json_response(writer, status, result)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if len(line) > 4096:
                await self._response(writer, "414 URI Too Long", "ERROR\n")
                return
            parts = line.decode("ascii", "replace").strip().split()
            if len(parts) != 3 or parts[0] not in {"GET", "POST"}:
                await self._response(writer, "400 Bad Request", "ERROR\n")
                return
            method = parts[0]
            content_length = 0
            while True:
                h = await asyncio.wait_for(reader.readline(), timeout=5)
                if h in (b"\r\n", b"\n", b""):
                    break
                if len(h) > 4096:
                    await self._response(writer, "431 Request Header Fields Too Large", "ERROR\n")
                    return
                name, _, value = h.decode("ascii", "replace").partition(":")
                if name.strip().lower() == "content-length":
                    try:
                        content_length = max(0, int(value.strip()))
                    except ValueError:
                        await self._response(writer, "400 Bad Request", "ERROR\n")
                        return
            if content_length > 16384:
                await self._response(writer, "413 Content Too Large", "ERROR\n")
                return
            body = b""
            if content_length:
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=5)

            u = urlsplit(parts[1])
            q = parse_qs(u.query, keep_blank_values=True)
            mode = q.get("mode", [""])[0]
            token = q.get("token", [""])[0]
            if not self.bus.authorized(token):
                await self._response(writer, "403 Forbidden", "FORBIDDEN\n")
                return

            if u.path == "/health":
                if method != "GET":
                    await self._response(writer, "405 Method Not Allowed", "METHOD_NOT_ALLOWED\n")
                    return
                await self._response(writer, "200 OK", "OK\n")
                return

            if u.path == "/test":
                if method != "GET":
                    await self._response(writer, "405 Method Not Allowed", "METHOD_NOT_ALLOWED\n")
                    return
                import time

                row = await self.bus.publish_order(
                    f"test-{time.time_ns()}",
                    "Тест Playerok Monitor",
                    "Проверка уведомления",
                    "test",
                )
                await self._response(writer, "200 OK", f"QUEUED\t{row.id}\n")
                return

            if u.path == "/cursor":
                if method != "GET":
                    await self._response(writer, "405 Method Not Allowed", "METHOD_NOT_ALLOWED\n")
                    return
                await self._response(
                    writer,
                    "200 OK",
                    json.dumps(
                        {"latest_event_id": self.bus.store.latest_event_id()},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "application/json; charset=utf-8",
                )
                return

            if u.path == "/relist":
                await self._relist_response(writer, method, q)
                return

            if u.path == "/wake":
                await self._wake_response(writer, method, q)
                return

            if u.path == "/fulfill":
                await self._fulfill_response(writer, method, q)
                return

            if u.path == "/poll" and mode == "auto_replies":
                await self._auto_replies_response(writer, method, body)
                return

            if u.path != "/poll":
                await self._response(writer, "404 Not Found", "NOT_FOUND\n")
                return

            if method != "GET":
                await self._response(writer, "405 Method Not Allowed", "METHOD_NOT_ALLOWED\n")
                return

            if mode == "orders":
                await self._orders_response(writer, q)
                return

            try:
                after = max(0, int(q.get("after", ["0"])[0]))
            except ValueError:
                after = 0
            row = await self.bus.wait_next(after)
            if row is None:
                await self._response(writer, "200 OK", "NONE\n")
            elif mode == "eventsv2":
                await self._response(
                    writer,
                    "200 OK",
                    "EVENT2\t%s\t%s\t%s\t%s\t%s\n"
                    % (
                        row.id,
                        _safe(row.kind),
                        _safe(row.deal_id),
                        _safe(row.title),
                        _safe(row.body),
                    ),
                )
            else:
                # Backward-compatible protocol for already installed Android builds.
                await self._response(
                    writer,
                    "200 OK",
                    f"EVENT\t{row.id}\t{_safe(row.title)}\t{_safe(row.body)}\n",
                )
        except Exception:
            log.exception("Poll connection failed")
            try:
                await self._response(writer, "500 Internal Server Error", "ERROR\n")
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
