from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_AUTO_REPLY_TEXT = (
    "Ожидайте, пожалуйста. Продавец скоро приступит к выполнению Вашего заказа."
)
DEFAULT_FULFILLMENT_REPLY_TEXT = (
    "Заказ выполнен. Пожалуйста, проверьте товар и подтвердите получение, если всё в порядке."
)
DEFAULT_SLEEP_REPLY_TEXT = (
    "Сейчас продавец может спать. Он увидит заказ после пробуждения и напишет вам."
)
DEFAULT_SLEEP_START = "00:00"
DEFAULT_SLEEP_END = "08:00"
DEFAULT_SLEEP_TIMEZONE = "Europe/Moscow"
MAX_AUTO_REPLY_MESSAGES = 8
MAX_AUTO_REPLY_MESSAGE_CHARS = 1000
MAX_AUTO_REPLY_TOTAL_CHARS = 4000


def normalize_messages(
    raw_messages: Iterable[Any] | None,
    fallback: str = DEFAULT_AUTO_REPLY_TEXT,
) -> tuple[str, ...]:
    """Validate and normalize the ordered auto-reply sequence.

    Empty fields are ignored. An entirely empty list deliberately falls back to
    the historical reply so a blank settings form keeps the existing default.
    """
    values = list(raw_messages or [])
    messages: list[str] = []
    seen: set[str] = set()
    total = 0
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Каждое сообщение должно быть текстом")
        message = value.strip()
        if not message:
            continue
        if len(message) > MAX_AUTO_REPLY_MESSAGE_CHARS:
            raise ValueError(
                f"Одно сообщение не может быть длиннее {MAX_AUTO_REPLY_MESSAGE_CHARS} символов"
            )
        if message in seen:
            raise ValueError("Одинаковые сообщения нельзя добавлять дважды")
        seen.add(message)
        messages.append(message)
        total += len(message)

    if not messages:
        message = (fallback or DEFAULT_AUTO_REPLY_TEXT).strip() or DEFAULT_AUTO_REPLY_TEXT
        messages = [message]
        total = len(message)

    if len(messages) > MAX_AUTO_REPLY_MESSAGES:
        raise ValueError(f"Можно добавить не больше {MAX_AUTO_REPLY_MESSAGES} сообщений")
    if total > MAX_AUTO_REPLY_TOTAL_CHARS:
        raise ValueError(
            f"Суммарная длина не может превышать {MAX_AUTO_REPLY_TOTAL_CHARS} символов"
        )
    return tuple(messages)


def normalize_clock_time(raw: Any, fallback: str) -> str:
    value = str(raw or fallback).strip()
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (TypeError, ValueError):
        raise ValueError("Время должно быть указано в формате ЧЧ:ММ") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Укажите корректное время от 00:00 до 23:59")
    return f"{hour:02d}:{minute:02d}"


def normalize_timezone(raw: Any) -> str:
    value = str(raw or DEFAULT_SLEEP_TIMEZONE).strip() or DEFAULT_SLEEP_TIMEZONE
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        raise ValueError("Неизвестный часовой пояс") from None
    return value


def _clock_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


@dataclass(frozen=True, slots=True)
class AutoReplyConfig:
    enabled: bool
    messages: tuple[str, ...]
    revision: int = 0
    updated_at: str = ""
    fulfillment_message: str = DEFAULT_FULFILLMENT_REPLY_TEXT
    sleep_enabled: bool = False
    sleep_start: str = DEFAULT_SLEEP_START
    sleep_end: str = DEFAULT_SLEEP_END
    sleep_timezone: str = DEFAULT_SLEEP_TIMEZONE
    sleep_message: str = DEFAULT_SLEEP_REPLY_TEXT

    def sleep_active_at(self, instant: datetime) -> bool:
        if not self.enabled or not self.sleep_enabled:
            return False
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        local = instant.astimezone(ZoneInfo(self.sleep_timezone))
        current = local.hour * 60 + local.minute
        start = _clock_minutes(self.sleep_start)
        end = _clock_minutes(self.sleep_end)
        if start < end:
            return start <= current < end
        return current >= start or current < end

    def payload(
        self,
        default_message: str = DEFAULT_AUTO_REPLY_TEXT,
        default_fulfillment_message: str = DEFAULT_FULFILLMENT_REPLY_TEXT,
        default_sleep_message: str = DEFAULT_SLEEP_REPLY_TEXT,
    ) -> dict[str, object]:
        # Defaults are returned as placeholders, not as editable values.  This
        # lets the Android form stay visually blank while the effective server
        # behavior remains explicit and backwards-compatible.
        custom_messages = [] if self.messages == (default_message,) else list(self.messages)
        custom_fulfillment = (
            ""
            if self.fulfillment_message == default_fulfillment_message
            else self.fulfillment_message
        )
        custom_sleep = (
            "" if self.sleep_message == default_sleep_message else self.sleep_message
        )
        return {
            "ok": True,
            "enabled": self.enabled,
            "messages": custom_messages,
            "effective_messages": list(self.messages),
            "fulfillment_message": custom_fulfillment,
            "effective_fulfillment_message": self.fulfillment_message,
            "sleep_enabled": self.sleep_enabled,
            "sleep_start": self.sleep_start,
            "sleep_end": self.sleep_end,
            "sleep_timezone": self.sleep_timezone,
            "sleep_message": custom_sleep,
            "effective_sleep_message": self.sleep_message,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "default_message": default_message,
            "default_fulfillment_message": default_fulfillment_message,
            "default_sleep_message": default_sleep_message,
            "limits": {
                "max_messages": MAX_AUTO_REPLY_MESSAGES,
                "max_message_chars": MAX_AUTO_REPLY_MESSAGE_CHARS,
                "max_total_chars": MAX_AUTO_REPLY_TOTAL_CHARS,
            },
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
