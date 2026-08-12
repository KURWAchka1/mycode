from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from PyPlayerokAPI.account import AccountClient

from .config import Settings, playerok_identity_from_token
from .db import OrderStore
from .event_bus import EventBus, PollServer
from .playerok_watcher import PlayerokOrderWatcher
from .processor import OrderProcessor
from .relist import RelistService


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main() -> None:
    settings = Settings.load()
    configure_logging(settings.log_level)
    log = logging.getLogger("playerok-monitor")

    store = OrderStore(settings.database_path)
    bus = EventBus(store, settings.api_token)
    poll = PollServer(
        bus,
        settings.poll_host,
        settings.poll_port,
        default_auto_reply_enabled=settings.auto_reply_enabled,
        default_auto_reply_text=settings.auto_reply_text,
    )

    watcher: PlayerokOrderWatcher | None = None
    tasks: list[asyncio.Task[Any]] = []

    try:
        await poll.start()

        account = AccountClient(
            token=settings.playerok_token,
            user_agent=settings.playerok_user_agent,
        )
        own_user_id, username = playerok_identity_from_token(settings.playerok_token)
        if not own_user_id:
            # Compatibility fallback for a future non-JWT authentication format.
            profile = await account.me
            own_user_id = str(getattr(profile, "id", "") or "")
            username = str(getattr(profile, "username", "") or "")
        log.info(
            "Playerok session OK user=%s id=%s",
            username or "?",
            own_user_id or "?",
        )

        processor = OrderProcessor(settings, store, bus, account, own_user_id)
        poll.order_processor = processor
        poll.relist_service = RelistService(
            account,
            store,
            own_user_id,
            raw=processor.raw,
            user_agent=settings.playerok_user_agent,
        )
        watcher = PlayerokOrderWatcher(account, processor, store, own_user_id)
        await watcher.start()

        tasks = [
            asyncio.create_task(
                processor.retry_pending_forever(),
                name="retry-replies",
            ),
        ]

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass

        log.info(
            "Monitor ready: hybrid Playerok WS+HTTP watcher + Android long-poll + per-deal auto-reply"
        )
        await stop.wait()

    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if watcher is not None:
            try:
                await watcher.stop()
            except Exception:
                logging.getLogger("playerok-monitor").exception("Playerok watcher stop failed")

        try:
            await poll.close()
        except Exception:
            logging.getLogger("playerok-monitor").exception("Android poll server close failed")


if __name__ == "__main__":
    asyncio.run(main())
