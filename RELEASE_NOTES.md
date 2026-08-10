# Playerok Monitor 2.3.9 · One UI Workspace

- The main screen is rebuilt around Samsung's viewing/interaction split: a compact title, one calm live-status focus block, clear deal navigation and a useful empty state.
- Every icon and secondary action now uses a transparent background with a restrained One UI ripple. Primary actions use only a translucent blue wash and outline instead of a black button slab.
- “Новые заказы” no longer has a hard-coded height. Tabs expand with the system font, keep the full label visible and are smoke-tested at 200% text size.
- Order cards now prioritize status, product name and payout without squeezing the title. A slim semantic rail distinguishes new, fulfilled, completed, problem and refund states.
- Dark mode uses layered charcoal-blue surfaces rather than pure-black controls, while light mode uses the same hierarchy and contrast.
- Settings and relisting inputs resize above the on-screen keyboard, add an IME-aware bottom inset and scroll the focused field into view.
- CI captures both default and 200%-text Android 16 screenshots in addition to linting, installing and launching the APK.

## Included from 2.3.8

- The app now opens on a dedicated “Новые заказы” tab containing only active sales that you have not yet marked as fulfilled.
- A separate configurable buyer message is sent only after you confirm fulfillment of your own sale. Fulfillment by another seller in your purchases is explicitly excluded.
- Fulfillment replies are journaled per order, checked against the chat and retried idempotently; service restarts and historical orders cannot create a catch-up message flood.
- Default message texts are now true field hints. Leaving a field blank visibly keeps it empty while the gray background text remains the effective server default.
- The global “Отключить сообщения” switch covers both payment and fulfillment messages and preserves every custom text.

## Included from 2.3.7

- The new relisting price field is optional. Leaving it blank reuses the sold item's original pre-discount listing price.
- A custom price remains visible when editing the confirmation, while an already-created draft continues to show its pinned price.

## Included from 2.3.6

- Removed the misleading duplicate “Получение подтвердил” row from order details.
- Purchases now communicate receipt unambiguously as “Получение вами”, while sales use “Получение покупателем”.
- The confirmation timestamp remains visible, and automatic confirmation is still labelled explicitly.

## Included from 2.3.5

- The relisting flow now starts with a dedicated setup step where the new listing price can be entered explicitly.
- Premium can be switched on or off. The VPS strictly selects `PREMIUM` for paid promotion or `DEFAULT` for ordinary publication and never substitutes one for the other.
- Playerok conditions are recalculated for the exact chosen price and mode, then shown in a separate final confirmation before publication.
- Once a draft has been created, its listing price is pinned to the order so retries cannot create a duplicate. Promotion mode may still be changed safely.
- The published order card records both the chosen listing price and the actual publication fee.
- The two-note notification chime is substantially louder, with soft limiting and smooth fades to avoid clipping or a sharp, tiring sound.

## Included from 2.3.4

- Relisting now strictly selects Playerok's `PREMIUM` publication option and can never silently substitute the free `DEFAULT` option.
- The amount shown in confirmation is taken from Playerok's current `itemPriorityStatuses` response for the exact listing price.
- After creating the copy, the VPS requests the draft-specific Premium quote again. Any change in price, type or period stops publication and requires a fresh confirmation before Playerok can charge the balance.
- The confirmation now shows the original pre-discount listing price, the current discounted price, the Premium period and the exact calculation price.
- Premium is paid through Playerok's `LOCAL` transaction provider only after the user confirms the current amount.

## Included from 2.3.3

- Settings now contain an ordered auto-reply editor: add, edit, remove and save up to eight buyer messages.
- The exact “Отключить сообщения” switch pauses all server-side replies while preserving every saved text for later re-enabling.
- Leaving every field blank safely restores the existing VPS default: “Ожидайте, пожалуйста. Продавец скоро приступит к выполнению Вашего заказа.”
- Orders first seen while replies are disabled are never queued for catch-up, so turning the switch back on cannot create a notification flood.
- Each order pins its own message sequence. Retries verify each part inside that order’s chat interval and skip anything already sent after a partial timeout.
- Relisting now preserves the original pre-discount price and accepts a free draft publication option when it is no more expensive than the confirmed source option.

## Included from 2.3.2

- Sales now show both the buyer-facing deal price and Playerok's exact net transaction value for the seller.
- Financial state is explicit: pending, frozen or credited. The widget uses the net amount as its compact price; purchases and refunded deals keep their normal price.
- Existing sales are backfilled once with rate limiting, while only pending/frozen transactions are refreshed afterward.

## Included from 2.3.1

- Relisting is offered only for orders first seen after this server update. Every order already stored on the VPS at migration time is permanently excluded and hidden in the app.

## Included from 2.3.0

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
