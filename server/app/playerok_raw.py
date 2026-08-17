from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PyPlayerokAPI.graphql import build_query_payload
from PyPlayerokAPI.types.queries import PERSISTED_QUERIES

log = logging.getLogger(__name__)

_CAMEL_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_RE_2 = re.compile(r"([a-z0-9])([A-Z])")

# Playerok periodically changes/registers APQ hashes. Different maintained
# Playerok clients can therefore carry different valid hashes for the same
# operation. Keep a short compatibility set and cache whichever hash the live
# backend accepts. The first values below come from the currently maintained
# alleexxeeyy/PlayerokAPI implementation; the installed PyPlayerokAPI hash is
# appended dynamically as another candidate.
_KNOWN_APQ_HASHES: dict[str, tuple[str, ...]] = {
    "userChats": (
        "c1ddbcd7c8b87160ac25e0734f9dc32fc945287b056f4b14abf1473bfb1ad11a",
    ),
    "chatMessages": (
        "9b4e264ff1b20e0fd3929afe023dee8f50affc02b85f80cb4b3dc1516ecfbaa0",
        "1cabd4aee7c22353f49eaaff78ca82355e182f33a723d0fd92ccd36092917784",
    ),
    "deal": (
        "d0421fb8dea49652876d69b1a14ce2c715ea9c7127c48c85a78e06de31a845ae",
        "e572582c52871c15c3278d46c649c7ec70dd4711d80661a4aa3cc67b48823e3e",
    ),
    "deals": (
        "591b0e6d036c2120c8f95b97dbfdf5635df3747cd901f4895e009935229417ef",
    ),
    "item": (
        "1cdb4b335f6c119db77883451f41cef83fc449f79f021627f27b76ec49203487",
        "014b7824712618664cdfd3223504f52f785a46b06561dd9e9c0e9d2e4d8262c6",
    ),
    "itemPriorityStatuses": (
        "b922220c6f979537e1b99de6af8f5c13727daeff66727f679f07f986ce1c025a",
    ),
}


def _snake(name: str) -> str:
    name = _CAMEL_RE_1.sub(r"\1_\2", name)
    return _CAMEL_RE_2.sub(r"\1_\2", name).lower()


def to_node(value: Any) -> Any:
    """Convert raw GraphQL JSON to attribute-access objects without enums/Pydantic.

    Playerok can add enum values server-side before third-party SDK enums are
    updated (for example user role SECURITY). Raw conversion intentionally keeps
    such values as plain strings instead of rejecting the whole response.
    """
    if isinstance(value, list):
        return [to_node(item) for item in value]
    if not isinstance(value, dict):
        return value

    attrs: dict[str, Any] = {}
    for key, raw in value.items():
        converted = to_node(raw)
        if isinstance(key, str):
            if key.isidentifier():
                attrs[key] = converted
            snake = _snake(key)
            if snake.isidentifier():
                attrs[snake] = converted

    # Playerok's Chat JSON uses participants while the SDK model exposes users.
    if "participants" in attrs and "users" not in attrs:
        attrs["users"] = attrs["participants"]

    return SimpleNamespace(**attrs)


def _result(response: Any, field: str) -> Any:
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    result = data.get(field) if isinstance(data, dict) else None
    if result is None:
        raise RuntimeError(f"Playerok GraphQL returned no data.{field}")
    return result


def _page(raw: dict[str, Any], *, list_name: str) -> SimpleNamespace:
    edges = raw.get("edges") or []
    items = []
    for edge in edges:
        if isinstance(edge, dict) and edge.get("node") is not None:
            items.append(to_node(edge["node"]))
    info = to_node(raw.get("pageInfo") or {})
    return SimpleNamespace(
        **{
            list_name: items,
            "page_info": info,
            "total_count": raw.get("totalCount", len(items)),
        }
    )


def _persisted_payload(operation_name: str, variables: dict[str, Any], sha256_hash: str) -> dict[str, Any]:
    return {
        "operationName": operation_name,
        "variables": variables,
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": sha256_hash,
            }
        },
    }


def _is_persisted_query_not_found(exc: BaseException) -> bool:
    text = str(exc)
    return "PersistedQueryNotFound" in text or "PERSISTED_QUERY_NOT_FOUND" in text


class RawPlayerokAPI:
    """Small raw GraphQL facade for monitor-critical operations.

    It deliberately bypasses PyPlayerokAPI Pydantic models. Network transport
    and authentication still come from the installed PyPlayerokAPI. Persisted
    query hashes are selected dynamically from a compatibility set so a stale
    SDK APQ hash cannot disable paid-order history scanning.
    """

    def __init__(self, account: Any, own_user_id: str) -> None:
        self.account = account
        self.own_user_id = own_user_id
        self._working_apq: dict[str, str] = {}

    def _candidate_hashes(self, operation_name: str) -> list[str]:
        candidates: list[str] = []

        cached = self._working_apq.get(operation_name)
        if cached:
            candidates.append(cached)

        for value in _KNOWN_APQ_HASHES.get(operation_name, ()):
            if value and value not in candidates:
                candidates.append(value)

        installed = PERSISTED_QUERIES.get(operation_name)
        if installed and installed not in candidates:
            candidates.append(installed)

        return candidates

    async def _request_apq(
        self,
        *,
        operation_name: str,
        variables: dict[str, Any],
    ) -> Any:
        candidates = self._candidate_hashes(operation_name)
        if not candidates:
            raise RuntimeError(f"No persisted-query hash candidates for {operation_name}")

        last_exc: BaseException | None = None
        for index, sha256_hash in enumerate(candidates):
            try:
                payload = _persisted_payload(operation_name, variables, sha256_hash)
                response = await self.account.transport.request(method="get", payload=payload)
                previous = self._working_apq.get(operation_name)
                self._working_apq[operation_name] = sha256_hash
                if previous is None and operation_name in {"chatMessages", "deal"}:
                    log.info(
                        "Playerok APQ OK operation=%s hash=%s...",
                        operation_name,
                        sha256_hash[:12],
                    )
                elif previous != sha256_hash and index > 0:
                    log.info(
                        "Playerok APQ compatibility switched operation=%s hash=%s...",
                        operation_name,
                        sha256_hash[:12],
                    )
                return response
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                last_exc = exc
                if _is_persisted_query_not_found(exc):
                    continue
                raise

        assert last_exc is not None
        raise last_exc

    async def get_chats(
        self,
        *,
        count: int = 24,
        type_name: str | None = "PM",
        after_cursor: str | None = None,
    ) -> SimpleNamespace:
        response = await self._request_apq(
            operation_name="userChats",
            variables={
                "pagination": {"first": count, "after": after_cursor},
                "filter": {
                    "userId": self.own_user_id,
                    "type": type_name,
                    "status": None,
                },
                "hasSupportAccess": False,
            },
        )
        raw = _result(response, "chats")
        if not isinstance(raw, dict):
            raise TypeError("Playerok GraphQL data.chats is not an object")
        return _page(raw, list_name="chats")

    async def get_chat_messages(
        self,
        *,
        chat_id: str,
        count: int = 24,
        after_cursor: str | None = None,
    ) -> SimpleNamespace:
        response = await self._request_apq(
            operation_name="chatMessages",
            variables={
                "pagination": {"first": count, "after": after_cursor},
                "filter": {"chatId": chat_id},
                "hasSupportAccess": False,
                "showForbiddenImage": True,
            },
        )
        raw = _result(response, "chatMessages")
        if not isinstance(raw, dict):
            raise TypeError("Playerok GraphQL data.chatMessages is not an object")
        return _page(raw, list_name="messages")

    async def get_deal(self, deal_id: str) -> Any:
        response = await self._request_apq(
            operation_name="deal",
            variables={
                "id": deal_id,
                "hasSupportAccess": False,
                "showForbiddenImage": True,
            },
        )
        return to_node(_result(response, "deal"))

    async def get_item(self, item_id: str) -> Any:
        """Read any Item/MyItem variant without the SDK's strict model parser."""
        response = await self._request_apq(
            operation_name="item",
            variables={
                "id": item_id,
                "slug": None,
                "hasSupportAccess": False,
                "showForbiddenImage": True,
            },
        )
        return to_node(_result(response, "item"))

    async def get_item_by_slug(self, slug: str) -> Any:
        """Resolve the live listing behind an immutable deal-item snapshot."""
        response = await self._request_apq(
            operation_name="item",
            variables={
                "id": None,
                "slug": slug,
                "hasSupportAccess": False,
                "showForbiddenImage": True,
            },
        )
        return to_node(_result(response, "item"))

    async def get_item_priority_statuses(self, item_id: str, price: int) -> list[Any]:
        response = await self._request_apq(
            operation_name="itemPriorityStatuses",
            variables={"itemId": item_id, "price": int(price)},
        )
        raw = _result(response, "itemPriorityStatuses")
        if not isinstance(raw, list):
            raise TypeError("Playerok GraphQL data.itemPriorityStatuses is not a list")
        return [to_node(option) for option in raw]

    async def create_item(
        self,
        *,
        game_category_id: str,
        obtaining_type_id: str,
        name: str,
        price: int,
        description: str,
        options: list[Any],
        data_fields: list[Any],
        attachments: list[str],
    ) -> Any:
        """Create a DRAFT via multipart GraphQL and return unvalidated JSON."""
        operations = build_query_payload(
            operation_name="createItem",
            query_key="createItem",
            variables={
                "input": {
                    "gameCategoryId": game_category_id,
                    "obtainingTypeId": obtaining_type_id,
                    "name": name,
                    "price": int(price),
                    "description": description,
                    "attributes": {option.field: option.value for option in options},
                    "dataFields": [
                        {"fieldId": field.id, "value": field.value}
                        for field in data_fields
                    ],
                },
                "attachments": [None] * len(attachments),
            },
        )
        mapping: dict[str, list[str]] = {}
        with ExitStack() as stack:
            files: dict[str, Any] = {}
            for index, attachment in enumerate(attachments, start=1):
                key = str(index)
                mapping[key] = [f"variables.attachments.{index - 1}"]
                file_obj = await asyncio.to_thread(Path(attachment).open, "rb")
                stack.callback(file_obj.close)
                files[key] = file_obj
            payload = {
                "operations": json.dumps(operations, ensure_ascii=False),
                "map": json.dumps(mapping),
            }
            response = await self.account.transport.request(
                method="post",
                payload=payload,
                files=files,
            )
        return to_node(_result(response, "createItem"))

    async def publish_item(
        self,
        item_id: str,
        priority_status_id: str,
        *,
        keep_in_sale: bool = False,
    ) -> Any:
        payload = build_query_payload(
            operation_name="publishItem",
            query_key="publishItem",
            variables={
                "input": {
                    "transactionProviderId": "LOCAL",
                    "priorityStatuses": [priority_status_id],
                    "itemId": item_id,
                    "keepInSale": bool(keep_in_sale),
                }
            },
        )
        response = await self.account.transport.request(method="post", payload=payload)
        return to_node(_result(response, "publishItem"))

    async def update_deal_status(self, deal_id: str, status: str) -> Any:
        normalized = (status or "").strip().upper()
        if normalized not in {
            "PAID",
            "PENDING",
            "SENT",
            "CONFIRMED",
            "CONFIRMED_AUTOMATICALLY",
            "ROLLED_BACK",
        }:
            raise ValueError(f"Unsupported Playerok deal status: {status}")
        payload = build_query_payload(
            operation_name="updateDeal",
            query_key="updateDeal",
            variables={"input": {"id": deal_id, "status": normalized}},
        )
        response = await self.account.transport.request(method="post", payload=payload)
        return to_node(_result(response, "updateDeal"))

    async def get_deals(
        self,
        *,
        count: int = 24,
        direction_name: str | None = "OUT",
        after_cursor: str | None = None,
    ) -> SimpleNamespace:
        response = await self._request_apq(
            operation_name="deals",
            variables={
                "pagination": {"first": count, "after": after_cursor},
                "filter": {
                    "userId": self.own_user_id,
                    "direction": direction_name,
                    "status": None,
                },
                "showForbiddenImage": True,
            },
        )
        raw = _result(response, "deals")
        if not isinstance(raw, dict):
            raise TypeError("Playerok GraphQL data.deals is not an object")
        return _page(raw, list_name="deals")

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        mark_chat_as_read: bool = False,
    ) -> Any:
        # Monitor always uses False. Refuse hidden behavior instead of silently
        # changing read state if a future caller passes True.
        if mark_chat_as_read:
            raise ValueError("RawPlayerokAPI.send_message does not mark chats as read")

        payload = build_query_payload(
            operation_name="createChatMessage",
            query_key="createChatMessage",
            variables={
                "input": {
                    "chatId": chat_id,
                    "text": text,
                }
            },
        )
        response = await self.account.transport.request(method="post", payload=payload)
        return to_node(_result(response, "createChatMessage"))
