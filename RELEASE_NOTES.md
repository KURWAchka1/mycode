# Playerok Monitor 2.2.0 · One UI 8.5 Order Lifecycle

- Widget redesigned around Samsung's concise One UI information hierarchy: one calm surface, a compact header, a unified metric grid and no decorative chevron.
- Five responsive compositions now include a dedicated wide 4×1 strip. Layout density changes while text size remains readable.
- The heavy generated artwork and nested glass cards were removed; subtle tonal depth and restrained status color keep data legible on the home screen.
- Order cards and details show whether fulfillment was confirmed by the seller and whether receipt was confirmed by the recipient, including automatic confirmation.
- Playerok markers `ITEM_SENT`, `DEAL_CONFIRMED` and `DEAL_CONFIRMED_AUTOMATICALLY` are persisted on the VPS and synchronized through the orders API.
- First-time monitoring performs a silent cursor bootstrap. Historical test and real-order events are treated as a baseline; only events created afterward notify.
- Changing Pairing URL safely resets the local cursor and cached orders, while normal stop/start keeps the existing cursor.

The attached APK is CI-built, linted, Android 16 smoke-tested and signed for direct personal installation.
