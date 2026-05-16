from engines.time_filter import current_bot_mode
from runtime_scheduler_map import get_scheduler_map
from utils.market_hours import as_ist_datetime


def get_due_tasks(value=None):
    now = as_ist_datetime(value)
    mode = current_bot_mode(now)
    scheduler_map = get_scheduler_map(mode)

    due_tasks = list(scheduler_map.get("every_1_second", []))

    second = now.second
    minute = now.minute

    if second % 5 == 0:
        due_tasks.extend(scheduler_map.get("every_5_seconds", []))

    if second % 10 == 0:
        due_tasks.extend(scheduler_map.get("every_10_seconds", []))

    if second == 0:
        due_tasks.extend(scheduler_map.get("every_1_minute", []))

        if minute % 5 == 0:
            due_tasks.extend(scheduler_map.get("every_5_minutes", []))

        if minute % 15 == 0:
            due_tasks.extend(scheduler_map.get("every_15_minutes", []))

        if minute % 30 == 0:
            due_tasks.extend(scheduler_map.get("every_30_minutes", []))

        if minute == 0:
            due_tasks.extend(scheduler_map.get("every_1_hour", []))

    return {
        "timestamp_ist": now.isoformat(),
        "mode": mode,
        "due_tasks": due_tasks,
    }


if __name__ == "__main__":
    print(get_due_tasks())
