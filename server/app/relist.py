from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .db import OrderRow, OrderStore, RelistReceipt

if TYPE_CHECKING:
    from .playerok_raw import RawPlayerokAPI


log = logging.getLogger(__name__)

AttachmentLoader = Callable[[Any, Path, int], Awaitable[Path]]
_ALLOWED_IMAGE_HOSTS = {
    "i.playerok.com",
    "playerok.fra1.digitaloceanspaces.com",
}
_SAFE_IMAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,179}$")
_MAX_IMAGE_BYTES = 12 * 1024 * 1024
_MAX_ATTACHMENTS = 10
_RELIST_PRIORITY_TYPE = "PREMIUM"
_RELIST_PRIORITY_TYPES = frozenset({"PREMIUM", "DEFAULT"})
_MAX_LISTING_PRICE = 10_000_000


class RelistError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "name", value) or "")


def _status(value: Any) -> str:
    return _text(value).strip().upper().rsplit(".", 1)[-1]


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _listing_price(item: Any) -> int:
    """Use Playerok rawPrice (price before seller discount), with price as fallback."""
    raw_price = _positive_int(_value(item, "raw_price", 0))
    return raw_price or _positive_int(_value(item, "price", 0))


def _item_url(slug: str) -> str:
    return f"https://playerok.com/products/{slug}" if slug else "https://playerok.com/profile"


def _recent_claim(started_at: str, minutes: int = 10) -> bool:
    try:
        value = started_at[:-1] + "+00:00" if started_at.endswith("Z") else started_at
        started = datetime.fromisoformat(value)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return started.astimezone(timezone.utc) >= datetime.now(timezone.utc) - timedelta(minutes=minutes)
    except (TypeError, ValueError):
        return False


def _allowed_image_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in _ALLOWED_IMAGE_HOSTS


def _attachment_urls(attachment: Any) -> list[str]:
    """Prefer the unwatermarked Playerok object, then fall back to its CDN URL."""
    result: list[str] = []
    filename = Path(_text(_value(attachment, "filename"))).name
    if filename and _SAFE_IMAGE_NAME.fullmatch(filename):
        origin = (
            "https://playerok.fra1.digitaloceanspaces.com/images/"
            + quote(filename, safe="")
        )
        result.append(origin)

    public_url = _text(_value(attachment, "url"))
    if public_url and _allowed_image_url(public_url) and public_url not in result:
        result.append(public_url)
    return result


def _image_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ""


def _download_image(url: str, user_agent: str) -> tuple[bytes, str]:
    if not _allowed_image_url(url):
        raise ValueError("image host is not allowed")
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8",
        },
    )
    with urlopen(request, timeout=20) as response:
        if not _allowed_image_url(response.geturl()):
            raise ValueError("image redirect host is not allowed")
        length = response.headers.get("Content-Length", "")
        if length and int(length) > _MAX_IMAGE_BYTES:
            raise ValueError("image is too large")
        data = response.read(_MAX_IMAGE_BYTES + 1)
    if not data or len(data) > _MAX_IMAGE_BYTES:
        raise ValueError("invalid image size")
    extension = _image_extension(data)
    if not extension:
        raise ValueError("downloaded file is not a supported image")
    return data, extension


class RelistService:
    """Create one faithful draft and publish that draft once for a sold order."""

    ACTIVE_ITEM_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {"APPROVED", "PENDING_APPROVAL", "PENDING_MODERATION"}
    )
    PUBLISHED_ITEM_STATUSES: ClassVar[frozenset[str]] = ACTIVE_ITEM_STATUSES | {"SOLD"}
    NATIVE_RELIST_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {"SOLD", "DRAFT", "EXPIRED", "DECLINED"}
    )
    DEAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {"SENT", "CONFIRMED", "CONFIRMED_AUTOMATICALLY"}
    )

    def __init__(
        self,
        account: Any,
        store: OrderStore,
        own_user_id: str,
        *,
        raw: RawPlayerokAPI | None = None,
        publish_cooldown_seconds: float = 2.0,
        attachment_loader: AttachmentLoader | None = None,
        user_agent: str = "PlayerokMonitor/2.3",
    ) -> None:
        self.account = account
        self.store = store
        if raw is None:
            from .playerok_raw import RawPlayerokAPI

            raw = RawPlayerokAPI(account, own_user_id)
        self.raw = raw
        self.publish_cooldown_seconds = max(0.0, publish_cooldown_seconds)
        self.user_agent = user_agent
        self._attachment_loader = attachment_loader or self._download_attachment
        self._deal_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._playerok_slot = asyncio.Semaphore(1)
        self._last_publish_monotonic = 0.0

    async def _get_item(self, item_id: str) -> Any:
        raw_getter = getattr(self.raw, "get_item", None)
        if callable(raw_getter):
            return await raw_getter(item_id)
        return await self.account.get_item(id=item_id)

    async def _get_item_by_slug(self, slug: str) -> Any:
        raw_getter = getattr(self.raw, "get_item_by_slug", None)
        if callable(raw_getter):
            return await raw_getter(slug)
        return None

    async def _resolve_live_item(self, deal_item: Any) -> Any:
        """Resolve Playerok's mutable listing from an immutable deal snapshot.

        Deal payloads can contain a synthetic item id and the status captured at
        purchase time. Playerok's own UI resolves the current listing by slug.
        """
        slug = _text(_value(deal_item, "slug"))
        if slug:
            try:
                current = await self._get_item_by_slug(slug)
                if _text(_value(current, "id")):
                    return current
            except Exception as exc:
                if int(getattr(exc, "status_code", 0) or 0) == 404:
                    log.info("Playerok has no live item for slug=%s", slug)
                    return None
                log.exception("Playerok live item lookup failed slug=%s", slug)
                raise RelistError(
                    "NATIVE_LOOKUP_FAILED",
                    "Не удалось безопасно проверить штатное перевыставление Playerok. "
                    "Копия товара не создавалась — повторите позже",
                    502,
                ) from exc

        return None

    async def _get_priority_statuses(self, item_id: str, price: int) -> list[Any]:
        raw_getter = getattr(self.raw, "get_item_priority_statuses", None)
        if callable(raw_getter):
            return list(await raw_getter(item_id, price))
        return list(await self.account.get_item_priority_statuses(item_id, str(price)))

    async def _create_playerok_item(self, **payload: Any) -> Any:
        raw_creator = getattr(self.raw, "create_item", None)
        if callable(raw_creator):
            return await raw_creator(**payload)
        return await self.account.create_item(**payload)

    async def _publish_playerok_item(
        self,
        item_id: str,
        priority_id: str,
        *,
        keep_in_sale: bool = False,
    ) -> Any:
        raw_publisher = getattr(self.raw, "publish_item", None)
        if callable(raw_publisher):
            try:
                return await raw_publisher(
                    item_id,
                    priority_id,
                    keep_in_sale=keep_in_sale,
                )
            except TypeError as exc:
                if "keep_in_sale" not in str(exc):
                    raise
                return await raw_publisher(item_id, priority_id)
        return await self.account.publish_item(item_id, priority_id)

    @staticmethod
    def _validate_order(row: OrderRow | None) -> OrderRow:
        if row is None:
            raise RelistError("ORDER_NOT_FOUND", "Заказ не найден на VPS", 404)
        if not row.relist_eligible:
            raise RelistError(
                "LEGACY_ORDER",
                "Перевыставление доступно только для новых заказов после обновления",
                409,
            )
        if row.direction != "OUT":
            raise RelistError("NOT_A_SALE", "Перевыставлять можно только товар из вашей продажи")
        if row.rolled_back:
            raise RelistError("ORDER_REFUNDED", "По заказу оформлен возврат — перевыставление заблокировано", 409)
        if row.problem_active:
            raise RelistError("PROBLEM_ACTIVE", "Сначала решите активную проблему по заказу", 409)
        if not row.seller_fulfilled:
            raise RelistError("NOT_FULFILLED", "Сначала подтвердите выполнение заказа на Playerok", 409)
        return row

    @staticmethod
    def _receipt_payload(receipt: RelistReceipt, row: OrderRow | None) -> dict[str, object]:
        listing_price = row.relist_listing_price if row else 0
        return {
            "ok": True,
            "state": "PUBLISHED",
            "deal_id": receipt.deal_id,
            "item_name": row.item_name if row else "",
            "source_item_id": receipt.source_item_id,
            "published_item_id": receipt.published_item_id,
            "item_url": _item_url(receipt.published_item_slug or receipt.source_item_slug),
            "priority_price": receipt.priority_price,
            "priority_type": receipt.priority_type,
            "item_price": listing_price,
            "source_item_price": listing_price,
            "priority_calculation_price": listing_price,
            "price_locked": True,
            "published_at": receipt.published_at,
            "cover_preserved": True,
            "one_per_order": True,
            "already_published": True,
        }

    async def _download_attachment(self, attachment: Any, directory: Path, index: int) -> Path:
        last_error: Exception | None = None
        for url in _attachment_urls(attachment):
            try:
                data, extension = await asyncio.to_thread(
                    _download_image,
                    url,
                    self.user_agent,
                )
                target = directory / f"attachment-{index:02d}{extension}"
                await asyncio.to_thread(target.write_bytes, data)
                return target
            except Exception as exc:  # noqa: BLE001 - try the next trusted Playerok URL
                last_error = exc
        raise RuntimeError("Playerok attachment could not be downloaded") from last_error

    @staticmethod
    def _copy_spec(source: Any, listing_price: int | None = None) -> dict[str, object]:
        category_id = _text(_value(_value(source, "category"), "id"))
        obtaining_type_id = _text(_value(_value(source, "obtaining_type"), "id"))
        name = _text(_value(source, "name"))
        price = listing_price if listing_price is not None else _listing_price(source)
        if not category_id or not obtaining_type_id or not name or price <= 0:
            raise RelistError(
                "ITEM_DATA_MISSING",
                "Playerok не вернул категорию, способ получения, название или цену товара",
                409,
            )

        attributes = _value(source, "attributes", {}) or {}
        if isinstance(attributes, SimpleNamespace):
            attributes = {
                field: value
                for field, value in vars(attributes).items()
                if not field.startswith("__")
            }
        if not isinstance(attributes, dict):
            raise RelistError("ITEM_DATA_INVALID", "Playerok вернул некорректные параметры товара", 409)
        options = [SimpleNamespace(field=str(field), value=value) for field, value in attributes.items()]

        data_fields: list[SimpleNamespace] = []
        for field in _value(source, "data_fields", []) or []:
            if _status(_value(field, "type")) != "ITEM_DATA":
                continue
            field_id = _text(_value(field, "id"))
            value = _value(field, "value")
            if field_id and value is not None:
                data_fields.append(SimpleNamespace(id=field_id, value=value))

        return {
            "game_category_id": category_id,
            "obtaining_type_id": obtaining_type_id,
            "name": name,
            "price": price,
            "description": _text(_value(source, "description")),
            "options": options,
            "data_fields": data_fields,
            "source_attachments": list(
                cast(list[Any], _value(source, "attachments", []) or [])
            ),
        }

    async def _create_draft(self, source: Any, listing_price: int) -> Any:
        spec = self._copy_spec(source, listing_price)
        source_attachments = cast(list[Any], spec.pop("source_attachments"))
        if len(source_attachments) > _MAX_ATTACHMENTS:
            raise RelistError(
                "TOO_MANY_ATTACHMENTS",
                "У исходного товара слишком много вложений для безопасного копирования",
                409,
            )

        try:
            with tempfile.TemporaryDirectory(prefix="playerok-relist-") as temp:
                directory = Path(temp)
                attachments = [
                    str(await self._attachment_loader(attachment, directory, index))
                    for index, attachment in enumerate(source_attachments, start=1)
                ]
                draft = await self._create_playerok_item(
                    **spec,
                    attachments=attachments,
                )
        except RelistError:
            raise
        except Exception as exc:
            raise RelistError(
                "DRAFT_CREATE_FAILED",
                "Playerok не создал копию товара. Публикация не запускалась",
                502,
            ) from exc

        if not _text(_value(draft, "id")):
            raise RelistError(
                "DRAFT_CREATE_FAILED",
                "Playerok не вернул ID созданного черновика. Публикация не запускалась",
                502,
            )
        return draft

    async def _priority_offer(
        self,
        item_id: str,
        item_price: int,
        *,
        required_type: str = _RELIST_PRIORITY_TYPE,
    ) -> dict[str, object]:
        try:
            statuses = await self._get_priority_statuses(item_id, item_price)
        except Exception as exc:
            log.exception(
                "Playerok publication options lookup failed item=%s price=%s",
                item_id,
                item_price,
            )
            raise RelistError(
                "PUBLISH_OPTIONS_FAILED",
                "Playerok не вернул варианты публикации",
                502,
            ) from exc
        if not statuses:
            log.warning(
                "Playerok returned no publication options item=%s price=%s",
                item_id,
                item_price,
            )
            raise RelistError("NO_PUBLISH_OPTION", "Playerok не предложил вариант публикации", 409)
        normalized_type = _status(required_type)
        matching = [
            option
            for option in statuses
            if _status(_value(option, "type")) == normalized_type
        ]
        option_label = "Premium" if normalized_type == "PREMIUM" else "обычное размещение"
        option_code = "PREMIUM" if normalized_type == "PREMIUM" else "DEFAULT"
        if not matching:
            available = ", ".join(
                sorted({_status(_value(option, "type")) or "UNKNOWN" for option in statuses})
            )
            log.warning(
                "Required publication priority is unavailable item=%s price=%s "
                "required=%s available=%s",
                item_id,
                item_price,
                normalized_type,
                available or "NONE",
            )
            raise RelistError(
                f"{option_code}_UNAVAILABLE",
                f"Playerok не предложил {option_label} для этой копии товара. Публикация не выполнялась",
                409,
            )
        if len(matching) != 1:
            log.warning(
                "Ambiguous publication priority item=%s price=%s type=%s count=%s",
                item_id,
                item_price,
                normalized_type,
                len(matching),
            )
            raise RelistError(
                f"{option_code}_AMBIGUOUS",
                f"Playerok вернул несколько вариантов «{option_label}». Публикация остановлена без списания",
                409,
            )

        priority = matching[0]
        priority_id = _text(_value(priority, "id"))
        if not priority_id:
            raise RelistError("NO_PUBLISH_OPTION", "Playerok вернул некорректный вариант публикации", 409)
        price_range = _value(priority, "price_range")
        priority_price = max(0, int(_value(priority, "price", 0) or 0))
        priority_period_days = int(_value(priority, "period", 0) or 0)
        log.info(
            "Playerok publication quote item=%s type=%s listing_price=%s fee=%s period=%s range=%s..%s",
            item_id,
            normalized_type,
            item_price,
            priority_price,
            priority_period_days,
            _value(price_range, "min", ""),
            _value(price_range, "max", ""),
        )
        return {
            "priority_id": priority_id,
            "priority_name": _text(_value(priority, "name")),
            "priority_price": priority_price,
            "priority_type": normalized_type,
            "priority_period_days": priority_period_days,
            "priority_price_range_min": _positive_int(_value(price_range, "min", 0)),
            "priority_price_range_max": _positive_int(_value(price_range, "max", 0)),
            "priority_calculation_price": item_price,
        }

    @staticmethod
    def _listing_price_request(value: int | None) -> int | None:
        if value is None:
            return None
        try:
            price = int(value)
        except (TypeError, ValueError) as exc:
            raise RelistError("INVALID_LISTING_PRICE", "Укажите целую цену товара в рублях") from exc
        if price < 1 or price > _MAX_LISTING_PRICE:
            raise RelistError(
                "INVALID_LISTING_PRICE",
                f"Цена товара должна быть от 1 до {_MAX_LISTING_PRICE:,} ₽".replace(",", " "),
            )
        return price

    @staticmethod
    def _priority_type_request(value: str | None, *, allow_setup: bool = False) -> str | None:
        if allow_setup and value is None:
            return None
        normalized = _status(value or _RELIST_PRIORITY_TYPE)
        if normalized not in _RELIST_PRIORITY_TYPES:
            raise RelistError(
                "INVALID_PRIORITY_TYPE",
                "Выберите Premium либо обычное бесплатное размещение",
            )
        return normalized

    async def preview(
        self,
        deal_id: str,
        *,
        listing_price: int | None = None,
        priority_type: str | None = _RELIST_PRIORITY_TYPE,
    ) -> dict[str, object]:
        deal_id = (deal_id or "").strip()
        if not deal_id:
            raise RelistError("DEAL_ID_REQUIRED", "Не указан ID заказа")
        listing_price = self._listing_price_request(listing_price)
        priority_type = self._priority_type_request(priority_type, allow_setup=True)
        async with self._deal_locks[deal_id]:
            receipt = self.store.get_relist_receipt(deal_id)
            row = self.store.get(deal_id)
            if receipt is not None:
                return self._receipt_payload(receipt, row)
            self._validate_order(row)
            if row and row.relist_state == "PUBLISHING" and _recent_claim(row.relist_started_at):
                raise RelistError(
                    "RELIST_IN_PROGRESS",
                    "Перевыставление уже выполняется. Подождите несколько секунд",
                    409,
                )
            async with self._playerok_slot:
                return await self._load_offer(
                    deal_id,
                    row,
                    listing_price=listing_price,
                    required_type=priority_type,
                )

    async def _load_offer(
        self,
        deal_id: str,
        row: OrderRow | None,
        *,
        listing_price: int | None = None,
        required_type: str | None = _RELIST_PRIORITY_TYPE,
    ) -> dict[str, object]:
        row = self._validate_order(row)
        deal = await self.raw.get_deal(deal_id)
        if not deal:
            raise RelistError("DEAL_NOT_FOUND", "Playerok не вернул данные заказа", 404)
        if _status(_value(deal, "direction")) != "OUT":
            raise RelistError("NOT_A_SALE", "Playerok не подтвердил, что это ваша продажа", 409)
        deal_status = _status(_value(deal, "status"))
        if deal_status not in self.DEAL_STATUSES:
            raise RelistError(
                "DEAL_NOT_FINISHED",
                f"Заказ пока нельзя перевыставить: статус {deal_status or 'неизвестен'}",
                409,
            )

        item = _value(deal, "item")
        source_item_id = _text(_value(item, "id"))
        source_item_slug = _text(_value(item, "slug"))
        source_details = item
        discounted_price = _positive_int(_value(source_details, "price", 0))
        source_item_price = _listing_price(source_details)
        if not source_item_id or source_item_price <= 0:
            raise RelistError("ITEM_DATA_MISSING", "В заказе не хватает данных исходного товара", 409)

        # A deal contains an immutable purchase-time Item snapshot. Playerok's
        # own "relist" flow operates on the mutable listing resolved by slug.
        # Continue an already-created copy first; otherwise prefer the native
        # listing and never edit its price.
        draft_item_id = row.relist_draft_item_id
        if not draft_item_id:
            live_item = await self._resolve_live_item(item)
            if live_item is not None:
                live_id = _text(_value(live_item, "id"))
                live_slug = _text(_value(live_item, "slug")) or source_item_slug
                live_status = _status(_value(live_item, "status"))
                live_price = _listing_price(live_item)
                live_discounted_price = _positive_int(_value(live_item, "price", 0))
                if not live_id or live_price <= 0:
                    raise RelistError(
                        "ITEM_DATA_MISSING",
                        "Playerok не вернул ID или исходную цену товара для штатного перевыставления",
                        409,
                    )

                # An active listing is not proof that this order was relisted.
                # Playerok deal snapshots and live items can temporarily
                # disagree, and recording a receipt here would create a false
                # success without ever calling publishItem.
                if live_status in self.ACTIVE_ITEM_STATUSES:
                    raise RelistError(
                        "ITEM_ALREADY_ACTIVE",
                        "Карточка сейчас активна на Playerok. Сервер не запускал "
                        "перевыставление и ничего не оплачивал",
                        409,
                    )

                if live_status not in self.NATIVE_RELIST_STATUSES:
                    raise RelistError(
                        "ITEM_NOT_RELISTABLE",
                        f"Playerok не разрешает штатно перевыставить товар со статусом "
                        f"{live_status or 'неизвестен'}",
                        409,
                    )
                if listing_price is not None and listing_price != live_price:
                    raise RelistError(
                        "NATIVE_PRICE_LOCKED",
                        f"Штатное «Перевыставить» Playerok сохраняет цену {live_price} ₽ "
                        "и не позволяет её менять. Очистите поле новой цены",
                        409,
                    )

                if required_type is None:
                    priority: dict[str, object] = {
                        "priority_id": "",
                        "priority_name": "",
                        "priority_price": 0,
                        "priority_type": "",
                        "priority_period_days": 0,
                        "priority_price_range_min": 0,
                        "priority_price_range_max": 0,
                        "priority_calculation_price": live_price,
                    }
                else:
                    priority = await self._priority_offer(
                        live_id,
                        live_price,
                        required_type=required_type,
                    )
                attachments = _value(live_item, "attachments", []) or []
                return {
                    "ok": True,
                    "state": "READY",
                    "publish_mode": "PLAYEROK_NATIVE",
                    "deal_id": deal_id,
                    "item_name": _text(_value(live_item, "name")) or row.item_name,
                    "source_item_id": live_id,
                    "source_item_slug": live_slug,
                    "source_item_url": _item_url(live_slug),
                    "draft_item_id": "",
                    "item_price": live_price,
                    "source_item_price": live_price,
                    "discounted_price": live_discounted_price,
                    "price_uses_raw": bool(
                        live_price and live_price != live_discounted_price
                    ),
                    "price_customized": False,
                    "price_locked": True,
                    **priority,
                    "has_cover": bool(attachments),
                    "cover_preserved": True,
                    "one_per_order": True,
                    "already_published": False,
                    "warning": (
                        "Будет использовано штатное «Перевыставить» Playerok: "
                        "та же карточка, обложка, параметры и исходная цена."
                    ),
                }

        target_id = source_item_id
        target_price = source_item_price
        if draft_item_id:
            try:
                draft = await self._get_item(draft_item_id)
            except Exception as exc:
                raise RelistError(
                    "DRAFT_RECOVERY_REQUIRED",
                    "Не удалось проверить сохранённый черновик. Новый дубликат не создавался",
                    502,
                ) from exc
            draft_status = _status(_value(draft, "status"))
            if draft_status in self.PUBLISHED_ITEM_STATUSES:
                receipt, _ = self.store.mark_relist_published(
                    deal_id,
                    source_item_id=source_item_id,
                    source_item_slug=source_item_slug,
                    published_item_id=draft_item_id,
                    published_item_slug=_text(_value(draft, "slug")) or row.relist_draft_item_slug,
                    priority_price=row.relist_priority_price,
                    priority_type=row.relist_priority_type,
                )
                log.warning("Recovered published draft deal=%s item=%s", deal_id, draft_item_id)
                return self._receipt_payload(receipt, self.store.get(deal_id))
            if draft_status != "DRAFT":
                raise RelistError(
                    "DRAFT_NOT_PUBLISHABLE",
                    f"Сохранённый черновик нельзя опубликовать: статус {draft_status or 'неизвестен'}",
                    409,
                )
            target_id = draft_item_id
            target_price = (
                _listing_price(draft)
                or row.relist_listing_price
                or source_item_price
            )
            if listing_price is not None and listing_price != target_price:
                raise RelistError(
                    "PRICE_LOCKED",
                    f"Для этого заказа уже создан черновик с ценой {target_price} ₽. "
                    "Чтобы не создавать дубль, его цену теперь нельзя заменить",
                    409,
                )
        else:
            try:
                looked_up_source = await self._get_item(source_item_id)
            except Exception as exc:
                if int(getattr(exc, "status_code", 0) or 0) != 404:
                    raise RelistError(
                        "SOURCE_LOOKUP_FAILED",
                        "Playerok не вернул полную карточку исходного товара",
                        502,
                    ) from exc
                looked_up_source = None
            source_details = looked_up_source or item
            spec = self._copy_spec(source_details)
            source_item_price = int(str(spec["price"]))
            target_price = listing_price or source_item_price
            discounted_price = _positive_int(_value(source_details, "price", 0))

        priority: dict[str, object]
        if required_type is None:
            previous_type = _status(row.relist_priority_type)
            if previous_type not in _RELIST_PRIORITY_TYPES:
                previous_type = ""
            priority = {
                "priority_id": "",
                "priority_name": "",
                "priority_price": 0,
                "priority_type": previous_type,
                "priority_period_days": 0,
                "priority_price_range_min": 0,
                "priority_price_range_max": 0,
                "priority_calculation_price": target_price,
            }
        else:
            priority = await self._priority_offer(
                target_id,
                target_price,
                required_type=required_type,
            )
        attachments = _value(source_details, "attachments", []) or []
        return {
            "ok": True,
            "state": "READY",
            "publish_mode": "COPY_FALLBACK",
            "deal_id": deal_id,
            "item_name": _text(_value(source_details, "name")) or row.item_name,
            "source_item_id": source_item_id,
            "source_item_slug": source_item_slug,
            "source_item_url": _item_url(source_item_slug),
            "draft_item_id": draft_item_id,
            "item_price": target_price,
            "source_item_price": source_item_price,
            "discounted_price": discounted_price,
            "price_uses_raw": bool(source_item_price and source_item_price != discounted_price),
            "price_customized": target_price != source_item_price,
            "price_locked": bool(draft_item_id),
            **priority,
            "has_cover": bool(attachments),
            "cover_preserved": True,
            "one_per_order": True,
            "already_published": False,
            "warning": "Не перевыставляйте уникальный аккаунт или единичный товар, если категория Playerok этого не разрешает.",
        }

    async def execute(
        self,
        deal_id: str,
        *,
        confirmed_priority_id: str,
        confirmed_price: int,
        listing_price: int | None = None,
        priority_type: str = _RELIST_PRIORITY_TYPE,
    ) -> dict[str, object]:
        deal_id = (deal_id or "").strip()
        if not deal_id:
            raise RelistError("DEAL_ID_REQUIRED", "Не указан ID заказа")
        listing_price = self._listing_price_request(listing_price)
        normalized_priority_type = self._priority_type_request(priority_type)
        assert normalized_priority_type is not None
        async with self._deal_locks[deal_id]:
            receipt = self.store.get_relist_receipt(deal_id)
            row = self.store.get(deal_id)
            if receipt is not None:
                return self._receipt_payload(receipt, row)
            self._validate_order(row)

            async with self._playerok_slot:
                offer = await self._load_offer(
                    deal_id,
                    row,
                    listing_price=listing_price,
                    required_type=normalized_priority_type,
                )
                if str(offer.get("state", "")) == "PUBLISHED":
                    return offer
                offered_priority_id = str(offer["priority_id"])
                offered_price = int(str(offer["priority_price"]))
                if confirmed_priority_id != offered_priority_id or int(confirmed_price) != offered_price:
                    raise RelistError(
                        "OFFER_CHANGED",
                        "Стоимость или вариант публикации изменились. Откройте подтверждение ещё раз",
                        409,
                    )

                stale_before = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
                claimed_row, claimed = self.store.claim_relist(
                    deal_id,
                    source_item_id=str(offer["source_item_id"]),
                    source_item_slug=str(offer.get("source_item_slug", "")),
                    priority_price=offered_price,
                    priority_type=str(offer["priority_type"]),
                    listing_price=int(str(offer["item_price"])),
                    stale_before=stale_before,
                )
                if not claimed or claimed_row is None:
                    receipt = self.store.get_relist_receipt(deal_id)
                    if receipt is not None:
                        return self._receipt_payload(receipt, self.store.get(deal_id))
                    raise RelistError(
                        "RELIST_IN_PROGRESS",
                        "Перевыставление уже выполняется. Повторная публикация не запущена",
                        409,
                    )

                source_item_id = str(offer["source_item_id"])
                source_slug = str(offer.get("source_item_slug", ""))
                selected_priority_price = offered_price
                selected_priority_type = str(offer["priority_type"])

                if str(offer.get("publish_mode", "")) == "PLAYEROK_NATIVE":
                    try:
                        current = await self._resolve_live_item(
                            {"id": source_item_id, "slug": source_slug}
                        )
                    except Exception as exc:
                        self.store.mark_relist_failed(deal_id, "NATIVE_ITEM_LOOKUP_FAILED")
                        raise RelistError(
                            "NATIVE_LOOKUP_FAILED",
                            "Не удалось повторно проверить товар перед штатным перевыставлением. "
                            "Публикация не запускалась",
                            502,
                        ) from exc

                    if current is None:
                        self.store.mark_relist_failed(deal_id, "NATIVE_ITEM_NOT_FOUND")
                        raise RelistError(
                            "NATIVE_LOOKUP_FAILED",
                            "Playerok не вернул живую карточку перед штатным "
                            "перевыставлением. Публикация не запускалась",
                            409,
                        )

                    current_status = _status(_value(current, "status"))
                    if current_status in self.ACTIVE_ITEM_STATUSES:
                        self.store.mark_relist_failed(deal_id, "NATIVE_ITEM_ALREADY_ACTIVE")
                        raise RelistError(
                            "ITEM_ALREADY_ACTIVE",
                            "Карточка стала активной на Playerok до публикации. "
                            "Сервер ничего не оплачивал; обновите заказ",
                            409,
                        )
                    if current_status not in self.NATIVE_RELIST_STATUSES:
                        self.store.mark_relist_failed(
                            deal_id,
                            f"NATIVE_STATUS_{current_status or 'UNKNOWN'}",
                        )
                        raise RelistError(
                            "ITEM_NOT_RELISTABLE",
                            f"Статус товара изменился на {current_status or 'неизвестен'}. "
                            "Публикация не запускалась",
                            409,
                        )

                    current_price = _listing_price(current)
                    if current_price != int(str(offer["item_price"])):
                        self.store.mark_relist_failed(deal_id, "NATIVE_PRICE_CHANGED")
                        raise RelistError(
                            "OFFER_CHANGED",
                            "Исходная цена товара изменилась на Playerok. "
                            "Откройте подтверждение ещё раз",
                            409,
                        )
                    try:
                        current_offer = await self._priority_offer(
                            source_item_id,
                            current_price,
                            required_type=selected_priority_type,
                        )
                    except RelistError as exc:
                        self.store.mark_relist_failed(deal_id, exc.code)
                        raise
                    if (
                        str(current_offer["priority_id"]) != offered_priority_id
                        or int(str(current_offer["priority_price"])) != offered_price
                        or str(current_offer["priority_type"]) != selected_priority_type
                        or int(str(current_offer["priority_period_days"]))
                        != int(str(offer["priority_period_days"]))
                    ):
                        self.store.mark_relist_failed(deal_id, "NATIVE_OFFER_CHANGED")
                        raise RelistError(
                            "OFFER_CHANGED",
                            "Playerok изменил условия штатного перевыставления. "
                            "Откройте подтверждение ещё раз",
                            409,
                        )

                    wait_for = self.publish_cooldown_seconds - (
                        time.monotonic() - self._last_publish_monotonic
                    )
                    if wait_for > 0:
                        await asyncio.sleep(wait_for)

                    published = None
                    try:
                        published = await self._publish_playerok_item(
                            source_item_id,
                            offered_priority_id,
                            keep_in_sale=False,
                        )
                        self._last_publish_monotonic = time.monotonic()
                    except Exception as exc:
                        try:
                            accepted = await self._resolve_live_item(
                                {"id": source_item_id, "slug": source_slug}
                            )
                        except Exception:  # noqa: BLE001 - verify ambiguous outcome
                            accepted = None
                        if _status(_value(accepted, "status")) in self.ACTIVE_ITEM_STATUSES:
                            published = accepted
                            log.warning(
                                "Recovered accepted Playerok native relist deal=%s item=%s",
                                deal_id,
                                source_item_id,
                            )
                        else:
                            self.store.mark_relist_failed(
                                deal_id,
                                f"NATIVE_PUBLISH_FAILED_{type(exc).__name__}",
                            )
                            log.exception(
                                "Playerok native relist failed deal=%s item=%s",
                                deal_id,
                                source_item_id,
                            )
                            raise RelistError(
                                "PLAYEROK_PUBLISH_FAILED",
                                "Playerok не подтвердил штатное перевыставление. "
                                "Повтор безопасен: второй товар не создаётся",
                                502,
                            ) from exc

                    published_status = _status(_value(published, "status"))
                    if published_status not in self.ACTIVE_ITEM_STATUSES:
                        try:
                            verified = await self._resolve_live_item(
                                {"id": source_item_id, "slug": source_slug}
                            )
                        except Exception:  # noqa: BLE001 - mutation result checked below
                            verified = None
                        if _status(_value(verified, "status")) in self.ACTIVE_ITEM_STATUSES:
                            published = verified
                            published_status = _status(_value(verified, "status"))
                    if published_status not in self.ACTIVE_ITEM_STATUSES:
                        self.store.mark_relist_failed(
                            deal_id,
                            f"NATIVE_RESULT_{published_status or 'UNKNOWN'}",
                        )
                        raise RelistError(
                            "PLAYEROK_PUBLISH_FAILED",
                            "Playerok не вернул активный статус после штатного перевыставления",
                            502,
                        )
                    published_slug = _text(_value(published, "slug")) or source_slug
                    receipt, _ = self.store.mark_relist_published(
                        deal_id,
                        source_item_id=source_item_id,
                        source_item_slug=source_slug,
                        published_item_id=source_item_id,
                        published_item_slug=published_slug,
                        priority_price=offered_price,
                        priority_type=selected_priority_type,
                    )
                    log.info(
                        "Playerok native relist published exactly-once deal=%s item=%s fee=%s",
                        deal_id,
                        source_item_id,
                        offered_price,
                    )
                    return self._receipt_payload(receipt, self.store.get(deal_id))

                draft: Any = None
                draft_item_id = claimed_row.relist_draft_item_id
                if draft_item_id:
                    try:
                        draft = await self._get_item(draft_item_id)
                    except Exception as exc:
                        self.store.mark_relist_failed(deal_id, "DRAFT_LOOKUP_FAILED")
                        raise RelistError(
                            "DRAFT_RECOVERY_REQUIRED",
                            "Не удалось проверить сохранённый черновик. Новый дубликат не создавался",
                            502,
                        ) from exc
                else:
                    try:
                        source = await self._get_item(source_item_id)
                    except Exception as exc:
                        self.store.mark_relist_failed(deal_id, "SOURCE_LOOKUP_FAILED")
                        raise RelistError(
                            "SOURCE_LOOKUP_FAILED",
                            "Playerok не вернул полную карточку исходного товара",
                            502,
                        ) from exc
                    if _status(_value(source, "status")) != "SOLD":
                        self.store.mark_relist_failed(deal_id, "SOURCE_NOT_SOLD")
                        raise RelistError(
                            "ITEM_NOT_SOLD",
                            "Полная карточка исходного товара больше не имеет статус SOLD",
                            409,
                        )
                    try:
                        draft = await self._create_draft(
                            source,
                            int(str(offer["item_price"])),
                        )
                    except RelistError as exc:
                        self.store.mark_relist_failed(deal_id, exc.code)
                        log.exception("Relist draft creation failed deal=%s", deal_id)
                        raise
                    draft_item_id = _text(_value(draft, "id"))
                    _stored_row, stored = self.store.mark_relist_draft(
                        deal_id,
                        source_item_id=source_item_id,
                        draft_item_id=draft_item_id,
                        draft_item_slug=_text(_value(draft, "slug")),
                    )
                    if not stored:
                        self.store.mark_relist_failed(deal_id, "DRAFT_STATE_CONFLICT")
                        raise RelistError(
                            "DRAFT_STATE_CONFLICT",
                            "Черновик создан, но VPS не смог безопасно закрепить его за заказом. Публикация не запускалась",
                            409,
                        )

                draft_status = _status(_value(draft, "status"))
                if draft_status in self.PUBLISHED_ITEM_STATUSES:
                    published = draft
                else:
                    if draft_status != "DRAFT":
                        self.store.mark_relist_failed(deal_id, f"DRAFT_STATUS_{draft_status}")
                        raise RelistError(
                            "DRAFT_NOT_PUBLISHABLE",
                            f"Созданную копию нельзя опубликовать: статус {draft_status or 'неизвестен'}",
                            409,
                        )

                    # createItem may return only the draft identity/status and omit
                    # price fields. Never ask Playerok for publication options with
                    # price=0 in that case: use the raw (pre-discount) source price
                    # that was copied into the draft and shown to the user.
                    draft_price = _listing_price(draft) or _positive_int(
                        offer.get("item_price")
                    )
                    if draft_price <= 0:
                        self.store.mark_relist_draft(
                            deal_id,
                            source_item_id=source_item_id,
                            draft_item_id=draft_item_id,
                            draft_item_slug=_text(_value(draft, "slug")),
                        )
                        raise RelistError(
                            "DRAFT_PRICE_MISSING",
                            "Playerok не вернул цену созданной копии. Черновик сохранён, повтор не создаст дубль",
                            502,
                        )
                    draft_offer = await self._priority_offer(
                        draft_item_id,
                        draft_price,
                        required_type=str(offer["priority_type"]),
                    )
                    selected_priority_price = int(str(draft_offer["priority_price"]))
                    selected_priority_type = str(draft_offer["priority_type"])
                    selected_priority_period = int(str(draft_offer["priority_period_days"]))
                    offered_priority_period = int(str(offer["priority_period_days"]))
                    if (
                        selected_priority_price != offered_price
                        or selected_priority_type != str(offer["priority_type"])
                        or selected_priority_period != offered_priority_period
                    ):
                        log.warning(
                            "Playerok changed publication offer after draft creation "
                            "deal=%s draft=%s source_fee=%s source_type=%s "
                            "source_period=%s draft_fee=%s draft_type=%s "
                            "draft_period=%s draft_price=%s",
                            deal_id,
                            draft_item_id,
                            offered_price,
                            offer["priority_type"],
                            offered_priority_period,
                            draft_offer["priority_price"],
                            draft_offer["priority_type"],
                            selected_priority_period,
                            draft_price,
                        )
                        self.store.mark_relist_draft(
                            deal_id,
                            source_item_id=source_item_id,
                            draft_item_id=draft_item_id,
                            draft_item_slug=_text(_value(draft, "slug")),
                        )
                        raise RelistError(
                            "OFFER_CHANGED",
                            "Playerok уточнил точные условия размещения для созданной копии. Откройте подтверждение ещё раз",
                            409,
                        )

                    wait_for = self.publish_cooldown_seconds - (
                        time.monotonic() - self._last_publish_monotonic
                    )
                    if wait_for > 0:
                        await asyncio.sleep(wait_for)

                    published = None
                    try:
                        published = await self._publish_playerok_item(
                            draft_item_id,
                            str(draft_offer["priority_id"]),
                        )
                        self._last_publish_monotonic = time.monotonic()
                    except Exception as exc:
                        try:
                            current = await self._get_item(draft_item_id)
                        except Exception:  # noqa: BLE001 - mutation outcome is checked below
                            current = None
                        if _status(_value(current, "status")) in self.PUBLISHED_ITEM_STATUSES:
                            published = current
                            log.warning("Recovered accepted relist deal=%s item=%s", deal_id, draft_item_id)
                        else:
                            self.store.mark_relist_failed(deal_id, f"PUBLISH_FAILED_{type(exc).__name__}")
                            log.exception("Relist publish failed deal=%s item=%s", deal_id, draft_item_id)
                            raise RelistError(
                                "PLAYEROK_PUBLISH_FAILED",
                                "Playerok не подтвердил публикацию. Повтор продолжит тот же черновик без дубля",
                                502,
                            ) from exc

                published_item_id = _text(_value(published, "id")) or draft_item_id
                published_slug = (
                    _text(_value(published, "slug"))
                    or _text(_value(draft, "slug"))
                    or claimed_row.relist_draft_item_slug
                )
                receipt, _ = self.store.mark_relist_published(
                    deal_id,
                    source_item_id=source_item_id,
                    source_item_slug=source_slug,
                    published_item_id=published_item_id,
                    published_item_slug=published_slug,
                    priority_price=selected_priority_price,
                    priority_type=selected_priority_type,
                )
                log.info(
                    "Relist copy published exactly-once deal=%s source=%s item=%s fee=%s",
                    deal_id,
                    source_item_id,
                    published_item_id,
                    selected_priority_price,
                )
                return self._receipt_payload(receipt, self.store.get(deal_id))
