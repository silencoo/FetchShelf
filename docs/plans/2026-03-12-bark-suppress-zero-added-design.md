# Bark Suppression When No New Accounts Added

## Goal
Avoid sending Bark notifications for successful collect-monitor runs when no new accounts were added (added_accounts == 0). Error notifications must still be sent.

## Behavior
- If `success == True` and `summary.added_accounts <= 0`: return early and **do not** send Bark.
- If `success == False`: always send Bark (existing behavior).
- If `bark_url` is empty: keep existing behavior (no notification).

## Scope
- Change limited to `APIServer._notify_collect_monitor`.
- No UI/config changes.

## Data Flow
- `_run_collect_monitor_once` builds `summary` as before.
- `_notify_collect_monitor` reads `summary.added_accounts` to decide whether to send Bark.

## Testing
- Unit test: when `success=True` and `added_accounts=0`, `_send_bark_notification` must not be called.
- Unit test: when `success=False`, `_send_bark_notification` must be called even if `added_accounts=0`.

## Risks
Low. Behavior change is additive and only affects successful monitor notifications.
