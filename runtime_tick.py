from engines.time_filter import current_bot_mode
from runtime_scheduler_map import get_scheduler_map
from utils.market_hours import as_ist_datetime


_LAST_EMITTED_SLOTS = {}
_INTERVAL_SECONDS = {
    "every_1_second": 1,
    "every_5_seconds": 5,
    "every_10_seconds": 10,
    "every_1_minute": 60,
    "every_5_minutes": 300,
    "every_15_minutes": 900,
    "every_30_minutes": 1800,
    "every_1_hour": 3600,
}


def _slot_key(now, interval_seconds):
    return int(now.timestamp()) // interval_seconds


def _is_due(now, mode, interval_name, interval_seconds, value_was_provided):
    if value_was_provided:
        second = now.second
        minute = now.minute

        if interval_name == "every_5_seconds":
            return second % 5 == 0
        if interval_name == "every_10_seconds":
            return second % 10 == 0
        if interval_name == "every_1_minute":
            return second == 0
        if interval_name == "every_5_minutes":
            return second == 0 and minute % 5 == 0
        if interval_name == "every_15_minutes":
            return second == 0 and minute % 15 == 0
        if interval_name == "every_30_minutes":
            return second == 0 and minute % 30 == 0
        if interval_name == "every_1_hour":
            return second == 0 and minute == 0
        return False

    key = (mode, interval_name, interval_seconds)
    current_slot = _slot_key(now, interval_seconds)
    previous_slot = _LAST_EMITTED_SLOTS.get(key)
    if previous_slot is None:
        _LAST_EMITTED_SLOTS[key] = current_slot
        return int(now.timestamp()) % interval_seconds == 0

    if previous_slot == current_slot:
        return False

    _LAST_EMITTED_SLOTS[key] = current_slot
    return True


def _safe_task_name(task_name):
    if task_name != "scanner":
        return task_name
    from runtime_classic_engine import LEGACY_CLASSIC_FILTERS

    return "scanner" if LEGACY_CLASSIC_FILTERS else "mode_scanner_status"


def get_due_tasks(value=None):
    now = as_ist_datetime(value)
    value_was_provided = value is not None
    mode = current_bot_mode(now)
    scheduler_map = get_scheduler_map(mode)

    due_tasks = []

    for interval_name, tasks in scheduler_map.items():
        interval_seconds = _INTERVAL_SECONDS.get(interval_name)
        if interval_seconds is None:
            continue

        if interval_seconds == 1 or _is_due(
            now,
            mode,
            interval_name,
            interval_seconds,
            value_was_provided,
        ):
            due_tasks.extend(_safe_task_name(task) for task in tasks)

    return {
        "timestamp_ist": now.isoformat(),
        "mode": mode,
        "due_tasks": due_tasks,
    }


if __name__ == "__main__":
    print(get_due_tasks())
