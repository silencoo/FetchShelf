# Uptime Kuma Push For Account Batch Schedules

## Goal
Allow each account-batch schedule to optionally send a Uptime Kuma push notification when the schedule run completes. This applies to both automatic schedule runs and manual "立即执行" runs.

## Behavior
- Add optional field `uptime_kuma_url` to account-batch schedules.
- On schedule task completion, if `uptime_kuma_url` is set:
  - Send a GET request to the URL.
  - Append query parameters:
    - `status=up` on success, `status=down` on failure or partial failure.
    - `msg=<message>` containing task name, platform, result, and counts (success/failed/skipped).
- Failure to send the push should not change task status; log only.

## Status Decision
- `down` when:
  - UI task status is `failed`, or
  - Result data indicates failures (`failed > 0`) or no queued items.
- `up` otherwise.

## Scope
- Account-batch schedules only (not collect monitors).
- Add UI input for `uptime_kuma_url` when creating schedules.
- Include `uptime_kuma_url` in schedule create/list payloads.

## Data Flow
- Schedule creation stores `uptime_kuma_url` in the schedule payload.
- When a schedule enqueues a UI task, attach schedule metadata to the task:
  `schedule_id`, `schedule_name`, `schedule_platform`, `schedule_uptime_kuma_url`.
- `_execute_ui_task` inspects these fields after completion and triggers the push.

## Error Handling
- Empty or invalid URL: skip sending.
- HTTP errors/timeouts: log and continue.
- Preserve existing proxy/timeout behavior.

## Testing
- Manual verification:
  - Configure a schedule with a push URL and run via "立即执行".
  - Confirm Kuma receives `status` and `msg`.
  - Confirm automatic run also triggers push.

## Risks
Low. Adds a new optional field and a non-blocking outbound request after task completion.
