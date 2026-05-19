from engines.time_filter import current_bot_mode
from runtime_scheduler_map import get_scheduler_map
from utils.market_hours import as_ist_datetime


_LAST_EMITTED_SLOTS = {}


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


def get_due_tasks(value=None):
    now = as_ist_datetime(value)
    value_was_provided = value is not None
    mode = current_bot_mode(now)
    scheduler_map = get_scheduler_map(mode)

    due_tasks = list(scheduler_map.get("every_1_second", []))

    if _is_due(now, mode, "every_5_seconds", 5, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_5_seconds", []))

    if _is_due(now, mode, "every_10_seconds", 10, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_10_seconds", []))

    if _is_due(now, mode, "every_1_minute", 60, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_1_minute", []))

    if _is_due(now, mode, "every_5_minutes", 300, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_5_minutes", []))

    if _is_due(now, mode, "every_15_minutes", 900, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_15_minutes", []))

    if _is_due(now, mode, "every_30_minutes", 1800, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_30_minutes", []))

    if _is_due(now, mode, "every_1_hour", 3600, value_was_provided):
        due_tasks.extend(scheduler_map.get("every_1_hour", []))

    return {
        "timestamp_ist": now.isoformat(),
        "mode": mode,
        "due_tasks": due_tasks,
    }


if __name__ == "__main__":
    print(get_due_tasks())
