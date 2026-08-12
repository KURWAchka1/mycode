from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.auto_reply import DEFAULT_AUTO_REPLY_TEXT, normalize_messages
from app.config import playerok_identity_from_token
from app.db import OrderStore
from app.event_bus import EventBus, PollServer, _order_json
from app.processor import ITEM_PAID_TEXT, OrderProcessor
from app.relist import RelistError, RelistService


class OrderStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = OrderStore(Path(self.temp.name) / "orders.sqlite3")
        self.store.record(
            "deal-1",
            "chat-1",
            "Test item",
            "100 RUB",
            "buyer",
            direction="OUT",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_relist_eligibility_starts_only_after_migration(self) -> None:
        path = Path(self.temp.name) / "legacy.sqlite3"
        legacy = sqlite3.connect(path)
        legacy.execute(
            """CREATE TABLE orders (
                deal_id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                item_name TEXT NOT NULL DEFAULT '',
                price TEXT NOT NULL DEFAULT '',
                buyer TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                reply_attempted INTEGER NOT NULL DEFAULT 0,
                reply_sent INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT ''
            )"""
        )
        legacy.execute(
            """INSERT INTO orders
               (deal_id, chat_id, item_name, price, buyer, first_seen_at)
               VALUES ('legacy-deal', 'legacy-chat', 'Old item', '10 RUB', 'buyer', '2026-08-08T00:00:00Z')"""
        )
        legacy.commit()
        legacy.close()

        migrated = OrderStore(path)
        try:
            old_order = migrated.get("legacy-deal")
            self.assertIsNotNone(old_order)
            self.assertFalse(old_order.relist_eligible)
            self.assertFalse(_order_json(old_order)["relist_eligible"])

            new_order = migrated.record(
                "new-deal",
                "new-chat",
                "New item",
                "20 RUB",
                "buyer",
                direction="OUT",
            )
            self.assertTrue(new_order.relist_eligible)
            self.assertTrue(_order_json(new_order)["relist_eligible"])
        finally:
            migrated.close()

    def test_seller_net_amount_and_freeze_status_are_serialized(self) -> None:
        row = self.store.record(
            "deal-financial",
            "chat-financial",
            "Financial item",
            "659 ₽",
            "buyer",
            direction="OUT",
            seller_net_amount="593.1",
            seller_net_status="PROCESSING",
            seller_net_available_at="2026-08-10T20:53:36.629Z",
        )
        payload = _order_json(row)
        self.assertEqual("593.1", payload["seller_net_amount"])
        self.assertEqual("PROCESSING", payload["seller_net_status"])
        self.assertEqual(
            "2026-08-10T20:53:36.629Z",
            payload["seller_net_available_at"],
        )

        updated, changed = self.store.set_seller_financials(
            "deal-financial",
            amount="593.1",
            status="CONFIRMED",
            available_at="",
        )
        self.assertTrue(changed)
        self.assertIsNotNone(updated)
        self.assertEqual("CONFIRMED", updated.seller_net_status)
        self.assertEqual("", updated.seller_net_available_at)

        purchase = self.store.record(
            "deal-purchase",
            "chat-purchase",
            "Purchase",
            "100 ₽",
            "seller",
            direction="IN",
            seller_net_amount="90",
            seller_net_status="PROCESSING",
        )
        self.assertEqual("", purchase.seller_net_amount)

    def test_checkout_fields_are_normalized_persisted_and_serialized(self) -> None:
        deal = SimpleNamespace(
            obtaining_fields=[
                SimpleNamespace(label="Сервер", value="Moscow", copyable=True),
                SimpleNamespace(label="Никнейм игрока", value="Player_One", copyable=True),
                SimpleNamespace(label="Пустое", value="", copyable=False),
            ]
        )
        fields_json = OrderProcessor._buyer_fields_json(deal)
        self.store.record(
            "deal-fields",
            "chat-fields",
            "Field item",
            "100 ₽",
            "buyer",
            buyer_fields_json=fields_json,
            direction="OUT",
        )
        payload = _order_json(self.store.get("deal-fields"))
        self.assertEqual(
            [
                {"label": "Сервер", "value": "Moscow", "copyable": True},
                {"label": "Никнейм игрока", "value": "Player_One", "copyable": True},
            ],
            payload["buyer_fields"],
        )

    def test_detailed_checkout_lookup_marks_empty_fields_as_loaded(self) -> None:
        processor = OrderProcessor(
            SimpleNamespace(), self.store, SimpleNamespace(), object(), "owner"
        )
        empty_deal = SimpleNamespace(obtaining_fields=None)
        self.assertTrue(
            processor.persist_buyer_fields(
                "deal-1", empty_deal, details_loaded=True
            )
        )
        self.assertEqual("[]", self.store.get("deal-1").buyer_fields_json)
        self.assertFalse(
            processor.persist_buyer_fields(
                "deal-1", empty_deal, details_loaded=True
            )
        )

    def test_app_fulfillment_updates_only_own_sale_once(self) -> None:
        self.store.set_deal_progress("deal-1", deal_status="PAID")

        class FakeRaw:
            def __init__(self) -> None:
                self.status = "PAID"
                self.update_calls = 0

            async def get_deal(self, deal_id: str):
                return SimpleNamespace(
                    id=deal_id,
                    direction="OUT",
                    status=self.status,
                    has_problem=False,
                    obtaining_fields=[],
                    testimonial=None,
                )

            async def update_deal_status(self, deal_id: str, status: str):
                self.update_calls += 1
                self.status = status
                return await self.get_deal(deal_id)

        async def scenario() -> None:
            raw = FakeRaw()
            processor = OrderProcessor(
                SimpleNamespace(), self.store, SimpleNamespace(), object(), "owner"
            )
            processor.raw = raw
            replies: list[str] = []

            async def capture_reply(row):
                replies.append(row.deal_id)
                self.store.set_fulfillment_reply_sent(row.deal_id, "reply-1")

            processor.ensure_fulfillment_reply = capture_reply
            first, second = await asyncio.gather(
                processor.request_fulfillment("deal-1"),
                processor.request_fulfillment("deal-1"),
            )
            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertEqual(1, raw.update_calls)
            self.assertEqual(["deal-1"], replies)
            row = self.store.get("deal-1")
            self.assertTrue(row.seller_fulfilled)
            self.assertEqual("SENT", row.deal_status)
            self.assertEqual("SELF", row.seller_fulfilled_by_relation)

        asyncio.run(scenario())

    def test_problem_actors_and_resolution_are_persisted(self) -> None:
        row, changed = self.store.set_problem(
            "deal-1",
            active=True,
            message_id="problem-1",
            event_at="2026-08-08T10:00:00+00:00",
            actor_name="buyer",
            actor_role="USER",
            actor_relation="COUNTERPARTY",
        )
        self.assertTrue(changed)
        self.assertTrue(row.problem_active)
        self.assertEqual("COUNTERPARTY", row.problem_reported_by_relation)

        row, changed = self.store.set_problem(
            "deal-1",
            active=False,
            message_id="resolved-1",
            event_at="2026-08-08T10:05:00+00:00",
            actor_name="Security",
            actor_role="SECURITY",
            actor_relation="PLAYEROK",
        )
        self.assertTrue(changed)
        self.assertFalse(row.problem_active)
        self.assertEqual("PLAYEROK", row.problem_resolved_by_relation)

        _, duplicate = self.store.set_problem(
            "deal-1",
            active=False,
            message_id="resolved-1",
            event_at="2026-08-08T10:05:00+00:00",
            actor_name="Security",
            actor_role="SECURITY",
            actor_relation="PLAYEROK",
        )
        self.assertFalse(duplicate)

        # The watcher replays recent chat history oldest-to-newest every minute.
        # An already resolved cycle must never be reactivated by its old marker.
        row, replayed = self.store.set_problem(
            "deal-1",
            active=True,
            message_id="problem-1",
            event_at="2026-08-08T10:00:00+00:00",
            actor_name="buyer",
            actor_role="USER",
            actor_relation="COUNTERPARTY",
        )
        self.assertFalse(replayed)
        self.assertFalse(row.problem_active)

    def test_rollback_actor_is_idempotent_and_serialized(self) -> None:
        row, changed = self.store.set_rolled_back(
            "deal-1",
            message_id="rollback-1",
            event_at="2026-08-08T11:00:00+00:00",
            actor_name="owner",
            actor_role="USER",
            actor_relation="SELF",
        )
        self.assertTrue(changed)
        self.assertTrue(row.rolled_back)
        self.assertEqual("SELF", row.rolled_back_by_relation)
        self.assertTrue(_order_json(row)["rolled_back"])

        _, duplicate = self.store.set_rolled_back(
            "deal-1",
            message_id="rollback-1",
            event_at="2026-08-08T11:00:00+00:00",
            actor_name="owner",
            actor_role="USER",
            actor_relation="SELF",
        )
        self.assertFalse(duplicate)

    def test_rollback_event_is_queued_once(self) -> None:
        row, _ = self.store.set_rolled_back(
            "deal-1",
            message_id="rollback-1",
            actor_relation="SELF",
        )
        bus = EventBus(self.store, "secret")
        first = asyncio.run(bus.publish_rollback(row, message_id="rollback-1"))
        second = asyncio.run(bus.publish_rollback(row, message_id="rollback-1"))
        self.assertEqual(first.id, second.id)
        self.assertEqual("DEAL_ROLLED_BACK", first.kind)

    def test_fulfillment_and_receipt_progress_is_monotonic(self) -> None:
        row, changed = self.store.set_deal_progress(
            "deal-1",
            deal_status="SENT",
            seller_fulfilled=True,
            seller_message_id="sent-1",
            seller_at="2026-08-08T12:00:00+00:00",
            actor_relation="SELF",
        )
        self.assertTrue(changed)
        self.assertTrue(row.seller_fulfilled)
        self.assertFalse(row.recipient_confirmed)

        row, changed = self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED_AUTOMATICALLY",
            recipient_confirmed=True,
            recipient_message_id="confirmed-1",
            recipient_at="2026-08-08T13:00:00+00:00",
            recipient_automatic=True,
            actor_relation="PLAYEROK",
        )
        self.assertTrue(changed)
        self.assertTrue(row.recipient_confirmed)
        self.assertTrue(row.recipient_confirmation_automatic)

        # Replaying the older ITEM_SENT marker must not regress CONFIRMED.
        row, replayed = self.store.set_deal_progress(
            "deal-1",
            deal_status="SENT",
            seller_fulfilled=True,
            seller_message_id="sent-1",
            seller_at="2026-08-08T12:00:00+00:00",
            actor_relation="SELF",
        )
        self.assertFalse(replayed)
        self.assertEqual("CONFIRMED_AUTOMATICALLY", row.deal_status)
        payload = _order_json(row)
        self.assertTrue(payload["seller_fulfilled"])
        self.assertTrue(payload["recipient_confirmed"])
        self.assertTrue(payload["recipient_confirmation_automatic"])

    def test_cursor_returns_latest_event_without_consuming_history(self) -> None:
        self.assertEqual(0, self.store.latest_event_id())
        bus = EventBus(self.store, "secret")
        first = asyncio.run(bus.publish_order("deal-1", "Test item", "100 RUB", "buyer"))
        self.assertEqual(first.id, self.store.latest_event_id())

    def test_retry_queue_contains_only_attempted_failed_replies(self) -> None:
        # Historical sales must never become a bulk auto-reply queue merely
        # because reply_sent is false after a migration or restart.
        self.assertEqual([], self.store.pending_replies())
        self.store.set_reply_attempted("deal-1")
        self.assertEqual(["deal-1"], [row.deal_id for row in self.store.pending_replies()])
        self.store.set_reply_sent("deal-1")
        self.assertEqual([], self.store.pending_replies())

    def test_auto_reply_settings_persist_and_blank_list_uses_default(self) -> None:
        initial = self.store.get_auto_reply_config(True, [DEFAULT_AUTO_REPLY_TEXT])
        self.assertTrue(initial.enabled)
        self.assertEqual((DEFAULT_AUTO_REPLY_TEXT,), initial.messages)

        saved = self.store.set_auto_reply_config(
            enabled=False,
            messages=["  Первое  ", "", "Второе"],
            fallback=DEFAULT_AUTO_REPLY_TEXT,
        )
        self.assertFalse(saved.enabled)
        self.assertEqual(("Первое", "Второе"), saved.messages)
        self.assertEqual(saved, self.store.get_auto_reply_config(True, [DEFAULT_AUTO_REPLY_TEXT]))

        blank = self.store.set_auto_reply_config(
            enabled=True,
            messages=["  "],
            fallback=DEFAULT_AUTO_REPLY_TEXT,
        )
        self.assertEqual((DEFAULT_AUTO_REPLY_TEXT,), blank.messages)
        with self.assertRaises(ValueError):
            normalize_messages(["Повтор", "Повтор"])

    def test_auto_reply_http_api_reads_and_updates_without_sending(self) -> None:
        async def scenario() -> None:
            server = PollServer(EventBus(self.store, "secret"), "127.0.0.1", 0)
            await server.start()
            try:
                port = server._server.sockets[0].getsockname()[1]

                async def request(method: str, body: str = "") -> tuple[int, dict]:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    raw = body.encode("utf-8")
                    writer.write(
                        (
                            f"{method} /poll?token=secret&mode=auto_replies HTTP/1.1\r\n"
                            "Host: localhost\r\n"
                            f"Content-Length: {len(raw)}\r\n"
                            "Connection: close\r\n\r\n"
                        ).encode("ascii") + raw
                    )
                    await writer.drain()
                    response = await reader.read()
                    writer.close()
                    await writer.wait_closed()
                    head, payload = response.split(b"\r\n\r\n", 1)
                    status = int(head.split(b" ", 2)[1])
                    return status, json.loads(payload.decode("utf-8"))

                status, initial = await request("GET")
                self.assertEqual(200, status)
                self.assertTrue(initial["enabled"])
                status, saved = await request(
                    "POST",
                    json.dumps({"enabled": False, "messages": ["A", "B"]}),
                )
                self.assertEqual(200, status)
                self.assertFalse(saved["enabled"])
                self.assertEqual(["A", "B"], saved["messages"])
            finally:
                await server.close()

        asyncio.run(scenario())

    def test_disabled_auto_reply_does_not_send_or_create_future_backlog(self) -> None:
        self.store.set_auto_reply_config(
            enabled=False,
            messages=["Не отправлять"],
            fallback=DEFAULT_AUTO_REPLY_TEXT,
        )
        settings = SimpleNamespace(
            auto_reply_enabled=True,
            auto_reply_text=DEFAULT_AUTO_REPLY_TEXT,
        )
        processor = OrderProcessor(settings, self.store, SimpleNamespace(), object(), "owner")

        class NoSendRaw:
            async def send_message(self, **kwargs):
                raise AssertionError("send_message must not be called while disabled")

        processor.raw = NoSendRaw()
        asyncio.run(processor.ensure_auto_reply(self.store.get("deal-1")))
        row = self.store.get("deal-1")
        self.assertTrue(row.reply_sent)
        self.assertFalse(row.reply_attempted)
        self.assertEqual([], self.store.pending_replies())

    def test_multi_message_retry_uses_order_snapshot_without_duplicates(self) -> None:
        paid_at = datetime.now(timezone.utc).isoformat()
        self.store.record(
            "deal-1",
            "chat-1",
            "Test item",
            "100 RUB",
            "buyer",
            payment_message_id="paid-1",
            payment_created_at=paid_at,
            direction="OUT",
        )
        self.store.set_auto_reply_config(
            enabled=True,
            messages=["Первое", "Второе"],
            fallback=DEFAULT_AUTO_REPLY_TEXT,
        )
        settings = SimpleNamespace(
            auto_reply_enabled=True,
            auto_reply_text=DEFAULT_AUTO_REPLY_TEXT,
        )
        processor = OrderProcessor(settings, self.store, SimpleNamespace(), object(), "owner")

        class PartialFailureRaw:
            def __init__(self) -> None:
                self.sent: list[str] = []
                self.fail_second_once = True
                self.messages = [SimpleNamespace(
                    id="paid-1",
                    text=ITEM_PAID_TEXT,
                    created_at=paid_at,
                    user=SimpleNamespace(id="buyer"),
                )]

            async def get_chat_messages(self, **kwargs):
                return SimpleNamespace(messages=list(self.messages))

            async def send_message(self, *, text: str, **kwargs):
                if text == "Второе" and self.fail_second_once:
                    self.fail_second_once = False
                    raise RuntimeError("simulated timeout")
                self.sent.append(text)
                message = SimpleNamespace(
                    id=f"sent-{len(self.sent)}",
                    text=text,
                    created_at=paid_at,
                    user=SimpleNamespace(id="owner"),
                )
                self.messages.append(message)
                return message

        raw = PartialFailureRaw()
        processor.raw = raw
        asyncio.run(processor.ensure_auto_reply(self.store.get("deal-1")))
        failed = self.store.get("deal-1")
        self.assertTrue(failed.reply_attempted)
        self.assertFalse(failed.reply_sent)
        self.assertEqual(["Первое", "Второе"], json.loads(failed.reply_messages_json))

        # A settings edit must not mutate an in-flight order sequence.
        self.store.set_auto_reply_config(
            enabled=True,
            messages=["Новый глобальный текст"],
            fallback=DEFAULT_AUTO_REPLY_TEXT,
        )
        asyncio.run(processor.ensure_auto_reply(self.store.get("deal-1")))
        self.assertEqual(["Первое", "Второе"], raw.sent)
        self.assertTrue(self.store.get("deal-1").reply_sent)

    def test_account_identity_is_read_from_jwt_without_network(self) -> None:
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "user-id",
            "identity": "seller",
        }).encode()).decode().rstrip("=")
        self.assertEqual(("user-id", "seller"), playerok_identity_from_token(f"x.{payload}.x"))
        self.assertEqual(("", ""), playerok_identity_from_token("not-a-jwt"))

    def test_database_allows_only_one_success_receipt_per_order(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        _, claimed = self.store.claim_relist(
            "deal-1",
            source_item_id="item-1",
            source_item_slug="item-one",
            priority_price=0,
            priority_type="DEFAULT",
            listing_price=100,
            stale_before="2000-01-01T00:00:00+00:00",
        )
        self.assertTrue(claimed)
        first, created = self.store.mark_relist_published(
            "deal-1",
            source_item_id="item-1",
            source_item_slug="item-one",
            published_item_id="item-1",
            published_item_slug="item-one",
            priority_price=0,
            priority_type="DEFAULT",
        )
        self.assertTrue(created)

        _, claimed_again = self.store.claim_relist(
            "deal-1",
            source_item_id="item-2",
            source_item_slug="item-two",
            priority_price=10,
            priority_type="PREMIUM",
            listing_price=200,
            stale_before="2100-01-01T00:00:00+00:00",
        )
        self.assertFalse(claimed_again)
        second, created_again = self.store.mark_relist_published(
            "deal-1",
            source_item_id="item-2",
            source_item_slug="item-two",
            published_item_id="item-2",
            published_item_slug="item-two",
            priority_price=10,
            priority_type="PREMIUM",
        )
        self.assertFalse(created_again)
        self.assertEqual(first.published_item_id, second.published_item_id)
        self.assertEqual("item-1", self.store.get("deal-1").relisted_item_id)

    def test_database_pins_one_draft_to_the_order(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        _, claimed = self.store.claim_relist(
            "deal-1",
            source_item_id="source-1",
            source_item_slug="source-one",
            priority_price=0,
            priority_type="DEFAULT",
            listing_price=125,
            stale_before="2000-01-01T00:00:00+00:00",
        )
        self.assertTrue(claimed)
        row, stored = self.store.mark_relist_draft(
            "deal-1",
            source_item_id="source-1",
            draft_item_id="draft-1",
            draft_item_slug="draft-one",
        )
        self.assertTrue(stored)
        self.assertEqual("DRAFT_READY", row.relist_state)
        self.assertEqual("draft-1", row.relist_draft_item_id)

        row, replaced = self.store.mark_relist_draft(
            "deal-1",
            source_item_id="source-1",
            draft_item_id="draft-2",
            draft_item_slug="draft-two",
        )
        self.assertFalse(replaced)
        self.assertEqual("draft-1", row.relist_draft_item_id)

    def test_copy_spec_uses_raw_price_and_raw_namespace_attributes(self) -> None:
        source = SimpleNamespace(
            category=SimpleNamespace(id="category-1"),
            obtaining_type=SimpleNamespace(id="obtaining-1"),
            name="Discounted item",
            price=80,
            raw_price=100,
            description="Description",
            attributes=SimpleNamespace(server="eu"),
            data_fields=[],
            attachments=[],
        )
        spec = RelistService._copy_spec(source)
        self.assertEqual(100, spec["price"])
        self.assertEqual("server", spec["options"][0].field)
        self.assertEqual("eu", spec["options"][0].value)
        custom = RelistService._copy_spec(source, 175)
        self.assertEqual(175, custom["price"])

    def test_concurrent_relist_requests_publish_only_once(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )

        source = SimpleNamespace(
            id="item-1",
            slug="sold-source-item",
            name="Test item",
            price=100,
            raw_price=125,
            status="SOLD",
            description="Exact description",
            category=SimpleNamespace(id="category-1"),
            obtaining_type=SimpleNamespace(id="obtaining-1"),
            attributes={"server": "eu", "platform": "android"},
            data_fields=[
                SimpleNamespace(id="secret-1", type="ITEM_DATA", value="delivery data"),
                SimpleNamespace(id="buyer-1", type="OBTAINING_DATA", value="must not copy"),
            ],
            attachments=[SimpleNamespace(
                id="cover-1",
                filename="cover-1.jpg",
                url="https://i.playerok.com/cover-1.jpg",
            )],
        )
        deal = SimpleNamespace(direction="OUT", status="CONFIRMED", item=source)

        class FakeRaw:
            async def get_deal(self, deal_id: str):
                self.deal_id = deal_id
                return deal

        class FakeAccount:
            def __init__(self) -> None:
                self.create_calls = 0
                self.publish_calls = 0
                self.draft = None
                self.created_payload = None
                self.priority_calls = []
                self.published_priority_id = ""

            async def get_item_priority_statuses(self, item_id: str, price: str):
                self.priority_calls.append((item_id, price))
                suffix = "draft" if item_id == "draft-1" else "source"
                return [
                    SimpleNamespace(
                        id=f"priority-default-{suffix}",
                        name="Обычное",
                        price=0,
                        type="DEFAULT",
                        period=30,
                    ),
                    SimpleNamespace(
                        id=f"priority-premium-{suffix}",
                        name="Премиум",
                        price=13,
                        type="PREMIUM",
                        period=30,
                    ),
                ]

            async def create_item(self, **payload):
                self.create_calls += 1
                self.created_payload = payload
                attachment = Path(payload["attachments"][0])
                self.attachment_existed_during_create = attachment.exists()
                self.attachment_bytes = attachment.read_bytes()
                self.draft = SimpleNamespace(
                    id="draft-1",
                    slug="copied-item",
                    name=payload["name"],
                    status="DRAFT",
                )
                return self.draft

            async def publish_item(self, item_id: str, priority_id: str):
                self.publish_calls += 1
                self.published_priority_id = priority_id
                await asyncio.sleep(0.02)
                self.draft.status = "APPROVED"
                return SimpleNamespace(id=item_id, slug="copied-item", status="APPROVED")

            async def get_item(self, *, id: str):
                if id == "item-1":
                    return source
                if id == "draft-1":
                    return self.draft
                return None

        async def load_attachment(attachment, directory: Path, index: int) -> Path:
            self.assertEqual("cover-1.jpg", attachment.filename)
            target = directory / f"source-{index}.jpg"
            target.write_bytes(b"\xff\xd8\xffexact-original-cover")
            return target

        async def scenario() -> None:
            account = FakeAccount()
            service = RelistService(
                account,
                self.store,
                "owner",
                raw=FakeRaw(),
                publish_cooldown_seconds=0,
                attachment_loader=load_attachment,
            )
            preview = await service.preview("deal-1")
            self.assertEqual("PREMIUM", preview["priority_type"])
            self.assertEqual(13, preview["priority_price"])
            self.assertEqual(125, preview["priority_calculation_price"])
            first, second = await asyncio.gather(
                service.execute(
                    "deal-1",
                    confirmed_priority_id="priority-premium-source",
                    confirmed_price=13,
                ),
                service.execute(
                    "deal-1",
                    confirmed_priority_id="priority-premium-source",
                    confirmed_price=13,
                ),
            )
            self.assertEqual(1, account.create_calls)
            self.assertEqual(1, account.publish_calls)
            self.assertEqual(
                [("item-1", "125"), ("item-1", "125"), ("draft-1", "125")],
                account.priority_calls,
            )
            self.assertTrue(account.attachment_existed_during_create)
            self.assertEqual(b"\xff\xd8\xffexact-original-cover", account.attachment_bytes)
            self.assertEqual("category-1", account.created_payload["game_category_id"])
            self.assertEqual("obtaining-1", account.created_payload["obtaining_type_id"])
            self.assertEqual("Exact description", account.created_payload["description"])
            self.assertEqual(125, account.created_payload["price"])
            self.assertEqual(2, len(account.created_payload["options"]))
            self.assertEqual(1, len(account.created_payload["data_fields"]))
            self.assertEqual("PUBLISHED", first["state"])
            self.assertEqual("draft-1", first["published_item_id"])
            self.assertEqual("priority-premium-draft", account.published_priority_id)
            self.assertEqual(13, first["priority_price"])
            self.assertEqual("PREMIUM", first["priority_type"])
            self.assertEqual(first["published_item_id"], second["published_item_id"])
            row = self.store.get("deal-1")
            self.assertEqual("draft-1", row.relist_draft_item_id)
            self.assertEqual("draft-1", row.relisted_item_id)

        asyncio.run(scenario())

    def test_custom_price_can_publish_with_free_default_option(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        source = SimpleNamespace(
            id="item-1",
            slug="sold-source-item",
            name="Test item",
            price=100,
            raw_price=125,
            status="SOLD",
            description="Description",
            category=SimpleNamespace(id="category-1"),
            obtaining_type=SimpleNamespace(id="obtaining-1"),
            attributes={},
            data_fields=[],
            attachments=[],
        )
        deal = SimpleNamespace(direction="OUT", status="CONFIRMED", item=source)

        class FakeRaw:
            async def get_deal(self, deal_id: str):
                return deal

        class FakeAccount:
            def __init__(self) -> None:
                self.priority_calls = []
                self.created_payload = None
                self.draft = None
                self.published_priority_id = ""

            async def get_item_priority_statuses(self, item_id: str, price: str):
                self.priority_calls.append((item_id, price))
                suffix = "draft" if item_id == "draft-1" else "source"
                return [
                    SimpleNamespace(
                        id=f"priority-default-{suffix}",
                        name="Обычное",
                        price=0,
                        type="DEFAULT",
                        period=30,
                    ),
                    SimpleNamespace(
                        id=f"priority-premium-{suffix}",
                        name="Премиум",
                        price=25,
                        type="PREMIUM",
                        period=30,
                    ),
                ]

            async def create_item(self, **payload):
                self.created_payload = payload
                self.draft = SimpleNamespace(
                    id="draft-1",
                    slug="copied-item",
                    price=payload["price"],
                    status="DRAFT",
                )
                return self.draft

            async def publish_item(self, item_id: str, priority_id: str):
                self.published_priority_id = priority_id
                self.draft.status = "APPROVED"
                return self.draft

            async def get_item(self, *, id: str):
                return source if id == "item-1" else self.draft

        async def scenario() -> None:
            account = FakeAccount()
            service = RelistService(
                account,
                self.store,
                "owner",
                raw=FakeRaw(),
                publish_cooldown_seconds=0,
            )
            setup = await service.preview("deal-1", priority_type=None)
            self.assertEqual(125, setup["item_price"])
            self.assertFalse(setup["price_locked"])
            self.assertEqual([], account.priority_calls)

            offer = await service.preview(
                "deal-1",
                listing_price=777,
                priority_type="DEFAULT",
            )
            self.assertEqual(777, offer["item_price"])
            self.assertEqual(125, offer["source_item_price"])
            self.assertTrue(offer["price_customized"])
            self.assertEqual("DEFAULT", offer["priority_type"])
            self.assertEqual(0, offer["priority_price"])

            result = await service.execute(
                "deal-1",
                confirmed_priority_id="priority-default-source",
                confirmed_price=0,
                listing_price=777,
                priority_type="DEFAULT",
            )
            self.assertEqual("PUBLISHED", result["state"])
            self.assertEqual("DEFAULT", result["priority_type"])
            self.assertEqual(0, result["priority_price"])
            self.assertEqual(777, account.created_payload["price"])
            self.assertEqual("priority-default-draft", account.published_priority_id)
            self.assertEqual(777, self.store.get("deal-1").relist_listing_price)
            self.assertEqual(
                [("item-1", "777"), ("item-1", "777"), ("draft-1", "777")],
                account.priority_calls,
            )

        asyncio.run(scenario())

    def test_publish_retry_reuses_saved_draft_without_creating_a_duplicate(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        source = SimpleNamespace(
            id="item-1",
            slug="sold-source-item",
            name="Test item",
            price=100,
            raw_price=125,
            status="SOLD",
            description="Description",
            category=SimpleNamespace(id="category-1"),
            obtaining_type=SimpleNamespace(id="obtaining-1"),
            attributes={},
            data_fields=[],
            attachments=[SimpleNamespace(filename="cover.jpg", url="https://i.playerok.com/cover.jpg")],
        )
        deal = SimpleNamespace(direction="OUT", status="CONFIRMED", item=source)

        class FakeRaw:
            async def get_deal(self, deal_id: str):
                return deal

        class FakeAccount:
            def __init__(self) -> None:
                self.create_calls = 0
                self.publish_calls = 0
                self.draft = None

            async def get_item_priority_statuses(self, item_id: str, price: str):
                suffix = "draft" if item_id == "draft-1" else "source"
                return [
                    SimpleNamespace(
                        id=f"priority-default-{suffix}",
                        name="Обычное",
                        price=0,
                        type="DEFAULT",
                        period=30,
                    ),
                    SimpleNamespace(
                        id=f"priority-premium-{suffix}",
                        name="Премиум",
                        price=13,
                        type="PREMIUM",
                        period=30,
                    ),
                ]

            async def create_item(self, **payload):
                self.create_calls += 1
                self.draft = SimpleNamespace(
                    id="draft-1",
                    slug="copied-item",
                    price=payload["price"],
                    status="DRAFT",
                )
                return self.draft

            async def publish_item(self, item_id: str, priority_id: str):
                self.publish_calls += 1
                if self.publish_calls == 1:
                    raise RuntimeError("simulated timeout")
                self.draft.status = "APPROVED"
                return self.draft

            async def get_item(self, *, id: str):
                return source if id == "item-1" else self.draft

        async def load_attachment(attachment, directory: Path, index: int) -> Path:
            target = directory / "cover.jpg"
            target.write_bytes(b"\xff\xd8\xffcover")
            return target

        async def scenario() -> None:
            account = FakeAccount()
            service = RelistService(
                account,
                self.store,
                "owner",
                raw=FakeRaw(),
                publish_cooldown_seconds=0,
                attachment_loader=load_attachment,
            )
            with self.assertRaises(RelistError) as failed:
                await service.execute(
                    "deal-1",
                    confirmed_priority_id="priority-premium-source",
                    confirmed_price=13,
                )
            self.assertEqual("PLAYEROK_PUBLISH_FAILED", failed.exception.code)
            failed_row = self.store.get("deal-1")
            self.assertEqual("FAILED", failed_row.relist_state)
            self.assertEqual("draft-1", failed_row.relist_draft_item_id)

            result = await service.execute(
                "deal-1",
                confirmed_priority_id="priority-premium-draft",
                confirmed_price=13,
            )
            self.assertEqual("PUBLISHED", result["state"])
            self.assertEqual("draft-1", result["published_item_id"])
            self.assertEqual(1, account.create_calls)
            self.assertEqual(2, account.publish_calls)

        asyncio.run(scenario())

    def test_changed_draft_premium_fee_requires_exact_reconfirmation(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        source = SimpleNamespace(
            id="item-1",
            slug="sold-source-item",
            name="Test item",
            price=100,
            raw_price=125,
            status="SOLD",
            description="Description",
            category=SimpleNamespace(id="category-1"),
            obtaining_type=SimpleNamespace(id="obtaining-1"),
            attributes={},
            data_fields=[],
            attachments=[],
        )
        deal = SimpleNamespace(direction="OUT", status="CONFIRMED", item=source)

        class FakeRaw:
            async def get_deal(self, deal_id: str):
                return deal

        class FakeAccount:
            def __init__(self) -> None:
                self.draft = None
                self.publish_calls = 0
                self.published_priority_id = ""

            async def get_item_priority_statuses(self, item_id: str, price: str):
                suffix = "draft" if item_id == "draft-1" else "source"
                # A sold item can show a discounted renewal fee, while a new
                # draft receives the full first-publication Premium price.
                premium_fee = 13 if item_id == "draft-1" else 9
                return [
                    SimpleNamespace(
                        id=f"priority-default-{suffix}",
                        name="Обычное",
                        price=0,
                        type="DEFAULT",
                        period=30,
                    ),
                    SimpleNamespace(
                        id=f"priority-premium-{suffix}",
                        name="Премиум",
                        price=premium_fee,
                        type="PREMIUM",
                        period=30,
                    ),
                ]

            async def create_item(self, **payload):
                self.draft = SimpleNamespace(
                    id="draft-1",
                    slug="copied-item",
                    price=payload["price"],
                    status="DRAFT",
                )
                return self.draft

            async def publish_item(self, item_id: str, priority_id: str):
                self.publish_calls += 1
                self.published_priority_id = priority_id
                self.draft.status = "APPROVED"
                self.draft.priority = "PREMIUM"
                return self.draft

            async def get_item(self, *, id: str):
                return source if id == "item-1" else self.draft

        async def scenario() -> None:
            account = FakeAccount()
            service = RelistService(
                account,
                self.store,
                "owner",
                raw=FakeRaw(),
                publish_cooldown_seconds=0,
            )
            with self.assertRaises(RelistError) as changed:
                await service.execute(
                    "deal-1",
                    confirmed_priority_id="priority-premium-source",
                    confirmed_price=9,
                    listing_price=777,
                    priority_type="PREMIUM",
                )
            self.assertEqual("OFFER_CHANGED", changed.exception.code)
            self.assertEqual(0, account.publish_calls)
            self.assertEqual("draft-1", self.store.get("deal-1").relist_draft_item_id)
            self.assertEqual(777, self.store.get("deal-1").relist_listing_price)

            with self.assertRaises(RelistError) as locked:
                await service.preview(
                    "deal-1",
                    listing_price=778,
                    priority_type="PREMIUM",
                )
            self.assertEqual("PRICE_LOCKED", locked.exception.code)

            exact = await service.preview("deal-1")
            self.assertEqual("priority-premium-draft", exact["priority_id"])
            self.assertEqual(13, exact["priority_price"])
            self.assertEqual(777, exact["item_price"])
            self.assertTrue(exact["price_locked"])
            result = await service.execute(
                "deal-1",
                confirmed_priority_id="priority-premium-draft",
                confirmed_price=13,
                listing_price=777,
                priority_type="PREMIUM",
            )
            self.assertEqual("PUBLISHED", result["state"])
            self.assertEqual(13, result["priority_price"])
            self.assertEqual("PREMIUM", result["priority_type"])
            self.assertEqual("priority-premium-draft", account.published_priority_id)

        asyncio.run(scenario())

    def test_playerok_native_relist_keeps_price_and_publishes_same_item_once(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        snapshot = SimpleNamespace(
            id="snapshot-1",
            slug="native-item",
            name="Native item",
            price=199,
            raw_price=199,
            status="APPROVED",
        )
        deal = SimpleNamespace(direction="OUT", status="CONFIRMED", item=snapshot)
        live = SimpleNamespace(
            id="live-1",
            slug="native-item",
            name="Native item",
            price=199,
            raw_price=199,
            status="SOLD",
            priority="PREMIUM",
            attachments=[SimpleNamespace(id="cover-1")],
        )
        stale_by_id = SimpleNamespace(
            id="live-1",
            slug="native-item",
            name="Native item",
            price=199,
            raw_price=199,
            status="APPROVED",
            priority="PREMIUM",
            attachments=[SimpleNamespace(id="cover-1")],
        )

        class FakeRaw:
            def __init__(self) -> None:
                self.publish_calls = 0
                self.keep_in_sale_values: list[bool] = []

            async def get_deal(self, deal_id: str):
                return deal

            async def get_item_by_slug(self, slug: str):
                self.slug = slug
                return live

            async def get_item(self, item_id: str):
                self.item_id = item_id
                return stale_by_id

            async def get_item_priority_statuses(self, item_id: str, price: int):
                self.priority_lookup = (item_id, price)
                return [
                    SimpleNamespace(
                        id="native-premium",
                        name="Премиум",
                        price=9,
                        type="PREMIUM",
                        period=30,
                    )
                ]

            async def publish_item(
                self,
                item_id: str,
                priority_id: str,
                *,
                keep_in_sale: bool = False,
            ):
                self.publish_calls += 1
                self.published = (item_id, priority_id)
                self.keep_in_sale_values.append(keep_in_sale)
                await asyncio.sleep(0.02)
                live.status = "APPROVED"
                return live

        async def scenario() -> None:
            raw = FakeRaw()
            service = RelistService(
                SimpleNamespace(),
                self.store,
                "owner",
                raw=raw,
                publish_cooldown_seconds=0,
            )

            setup = await service.preview("deal-1", priority_type=None)
            self.assertEqual("PLAYEROK_NATIVE", setup["publish_mode"])
            self.assertTrue(setup["price_locked"])
            self.assertEqual(199, setup["item_price"])
            self.assertEqual("live-1", setup["source_item_id"])

            with self.assertRaises(RelistError) as changed_price:
                await service.preview(
                    "deal-1",
                    listing_price=200,
                    priority_type="PREMIUM",
                )
            self.assertEqual("NATIVE_PRICE_LOCKED", changed_price.exception.code)
            self.assertEqual(0, raw.publish_calls)

            offer = await service.preview(
                "deal-1",
                listing_price=199,
                priority_type="PREMIUM",
            )
            self.assertEqual(9, offer["priority_price"])
            first, second = await asyncio.gather(
                service.execute(
                    "deal-1",
                    confirmed_priority_id="native-premium",
                    confirmed_price=9,
                    listing_price=199,
                    priority_type="PREMIUM",
                ),
                service.execute(
                    "deal-1",
                    confirmed_priority_id="native-premium",
                    confirmed_price=9,
                    listing_price=199,
                    priority_type="PREMIUM",
                ),
            )
            self.assertEqual(1, raw.publish_calls)
            self.assertEqual(("live-1", "native-premium"), raw.published)
            self.assertEqual([False], raw.keep_in_sale_values)
            self.assertEqual("PUBLISHED", first["state"])
            self.assertEqual("live-1", first["published_item_id"])
            self.assertEqual(first["published_item_id"], second["published_item_id"])

        asyncio.run(scenario())

    def test_playerok_native_active_item_is_not_recorded_as_a_success(self) -> None:
        self.store.set_deal_progress(
            "deal-1",
            deal_status="CONFIRMED",
            seller_fulfilled=True,
        )
        snapshot = SimpleNamespace(
            id="snapshot-1",
            slug="native-item",
            name="Native item",
            price=199,
            raw_price=199,
            status="APPROVED",
        )
        live = SimpleNamespace(
            id="live-1",
            slug="native-item",
            name="Native item",
            price=199,
            raw_price=199,
            status="APPROVED",
            priority="PREMIUM",
            attachments=[SimpleNamespace(id="cover-1")],
        )

        class FakeRaw:
            def __init__(self) -> None:
                self.publish_calls = 0

            async def get_deal(self, deal_id: str):
                return SimpleNamespace(
                    direction="OUT",
                    status="CONFIRMED",
                    item=snapshot,
                )

            async def get_item_by_slug(self, slug: str):
                return live

            async def publish_item(self, *args, **kwargs):
                self.publish_calls += 1
                raise AssertionError("active native item must not be paid twice")

        async def scenario() -> None:
            raw = FakeRaw()
            service = RelistService(
                SimpleNamespace(),
                self.store,
                "owner",
                raw=raw,
                publish_cooldown_seconds=0,
            )
            with self.assertRaises(RelistError) as active:
                await service.preview("deal-1", priority_type=None)
            self.assertEqual("ITEM_ALREADY_ACTIVE", active.exception.code)
            self.assertEqual(0, raw.publish_calls)
            self.assertIsNone(self.store.get_relist_receipt("deal-1"))
            self.assertNotEqual("PUBLISHED", self.store.get("deal-1").relist_state)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
