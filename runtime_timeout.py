import multiprocessing
import time
import traceback


MAX_RESULT_STRING_CHARS = 2000
MAX_RESULT_LIST_ITEMS = 20
MAX_RESULT_DICT_ITEMS = 40
MAX_RESULT_DEPTH = 3


def _safe_close(resource):
    try:
        resource.close()
    except (EOFError, BrokenPipeError, OSError, ValueError):
        pass


def _safe_send(result_conn, payload):
    try:
        result_conn.send(payload)
        return True
    except (BrokenPipeError, EOFError, OSError):
        return False


def _compact_for_pipe(value, depth=0):
    if depth >= MAX_RESULT_DEPTH:
        return "<compact_result_depth_limit>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= MAX_RESULT_STRING_CHARS:
            return value
        return value[:MAX_RESULT_STRING_CHARS] + "...<truncated>"
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        compacted = [_compact_for_pipe(item, depth + 1) for item in items[:MAX_RESULT_LIST_ITEMS]]
        if len(items) > MAX_RESULT_LIST_ITEMS:
            compacted.append(f"<{len(items) - MAX_RESULT_LIST_ITEMS} items truncated>")
        return compacted
    if isinstance(value, dict):
        compacted = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_RESULT_DICT_ITEMS:
                compacted["<truncated_keys>"] = len(value) - MAX_RESULT_DICT_ITEMS
                break
            compacted[str(key)[:200]] = _compact_for_pipe(item, depth + 1)
        return compacted
    return repr(value)[:MAX_RESULT_STRING_CHARS]


def _result_status(handler_result):
    if not isinstance(handler_result, dict):
        return "ok"
    status = str(handler_result.get("status") or "ok").lower()
    if status in {"error", "failed", "failure", "degraded", "timeout"}:
        return "error"
    return "ok"


def _run_handler(handler, result_conn):
    try:
        started_monotonic = time.monotonic()
        handler_result = handler()
        compact_result = _compact_for_pipe(handler_result)
        _safe_send(
            result_conn,
            {
                "status": _result_status(handler_result),
                "result": compact_result,
                "child_duration_seconds": round(time.monotonic() - started_monotonic, 3),
            }
        )
    except BaseException as exc:
        _safe_send(
            result_conn,
            {
                "status": "error",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        _safe_close(result_conn)


def _pipe_result(result_conn, process, result_grace_seconds):
    deadline = time.monotonic() + max(float(result_grace_seconds or 0), 0.0)

    while True:
        if result_conn.poll(0):
            try:
                return result_conn.recv()
            except (EOFError, BrokenPipeError, OSError):
                break

        if time.monotonic() >= deadline:
            break

        time.sleep(0.05)

    if process.exitcode == 0:
        return {"status": "ok"}

    return {
        "status": "error",
        "error": f"handler exited without result exitcode={process.exitcode}",
        "traceback": "",
        "termination_reason": "exited_without_result",
    }


def run_with_timeout(
    handler,
    timeout_seconds,
    *,
    terminate_grace_seconds=5,
    kill_grace_seconds=5,
    queue_grace_seconds=2,
):
    """
    Runs a top-level task handler with a hard timeout.

    A process boundary lets the dispatcher terminate blocked network/IO work
    without changing business logic inside the handler.
    """
    result_conn, child_result_conn = multiprocessing.Pipe(duplex=False)
    process = multiprocessing.Process(
        target=_run_handler,
        args=(handler, child_result_conn),
    )

    started_monotonic = time.monotonic()
    process_started = False
    try:
        process.start()
        process_started = True
        _safe_close(child_result_conn)
        timeout_seconds = max(float(timeout_seconds or 0), 0.0)
        terminate_grace_seconds = max(float(terminate_grace_seconds or 0), 0.0)
        kill_grace_seconds = max(float(kill_grace_seconds or 0), 0.0)
        process.join(timeout_seconds)

        if process.is_alive():
            timeout_at_seconds = round(time.monotonic() - started_monotonic, 3)
            process.terminate()
            terminate_deadline = time.monotonic() + terminate_grace_seconds
            while process.is_alive() and time.monotonic() < terminate_deadline:
                process.join(min(0.5, max(0.0, terminate_deadline - time.monotonic())))

            if process.is_alive():
                process.kill()
                process.join(kill_grace_seconds)
                termination_reason = "timeout_kill_after_terminate_grace"
            else:
                termination_reason = "timeout_terminate"

            return {
                "status": "timeout",
                "timeout_seconds": timeout_seconds,
                "exitcode": process.exitcode,
                "duration_seconds": round(time.monotonic() - started_monotonic, 3),
                "timeout_at_seconds": timeout_at_seconds,
                "termination_reason": termination_reason,
            }

        result = _pipe_result(result_conn, process, queue_grace_seconds)
        result["exitcode"] = process.exitcode
        result.setdefault("duration_seconds", round(time.monotonic() - started_monotonic, 3))
        return result
    finally:
        _safe_close(result_conn)
        _safe_close(child_result_conn)
        if process_started:
            try:
                if process.is_alive():
                    process.kill()
                    process.join(kill_grace_seconds)
            except (OSError, ValueError):
                pass
            try:
                if not process.is_alive():
                    process.close()
            except (OSError, ValueError):
                pass
