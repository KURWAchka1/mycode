# Playerok Monitor 2.3.0 · Safe One-tap Relist

- A completed sale can relist its original sold item directly from the order screen while preserving the same cover, description and fields.
- The app previews Playerok's current publication fee and requires an explicit confirmation before any paid action.
- Every source order has a hard one-success limit. Repeated taps, concurrent requests, network retries and VPS restarts return the first publication instead of creating a duplicate.
- Relisting is serialized and rate-limited on the VPS. Failed attempts can be retried safely; the order limit is consumed only after Playerok confirms publication.
- Refunded orders, active problems, purchases and sales not yet fulfilled are blocked from relisting.
- The order list and details show the relist state, date and publication price.

## Included from 2.2.0

- Widget redesigned around Samsung's concise One UI information hierarchy: one calm surface, a compact header, a unified metric grid and no decorative chevron.
- Five responsive compositions now include a dedicated wide 4×1 strip. Layout density changes while text size remains readable.
- The heavy generated artwork and nested glass cards were removed; subtle tonal depth and restrained status color keep data legible on the home screen.
- Order cards and details show whether fulfillment was confirmed by the seller and whether receipt was confirmed by the recipient, including automatic confirmation.
- Playerok markers `ITEM_SENT`, `DEAL_CONFIRMED` and `DEAL_CONFIRMED_AUTOMATICALLY` are persisted on the VPS and synchronized through the orders API.
- First-time monitoring performs a silent cursor bootstrap. Historical test and real-order events are treated as a baseline; only events created afterward notify.
- Changing Pairing URL safely resets the local cursor and cached orders, while normal stop/start keeps the existing cursor.

The attached APK is CI-built, linted, Android 16 smoke-tested and signed for direct personal installation.
