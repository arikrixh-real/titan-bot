import multiprocessing
import queue
import time
import traceback


def _run_handler(handler, result_queue):
    try:
        started_monotonic = time.monotonic()
        handler()
        result_queue.put(
            {
                "status": "ok",
                "child_duration_seconds": round(time.monotonic() - started_monotonic, 3),
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "status": "error",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        result_queue.close()
        result_queue.join_thread()


def _queue_result(result_queue, process, queue_grace_seconds):
    deadline = time.monotonic() + max(float(queue_grace_seconds or 0), 0.0)

    while True:
        try:
            return result_queue.get_nowait()
        except queue.Empty:
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
    result_queue = multiprocessing.Queue(maxsize=1)
    process = multiprocessing.Process(
        target=_run_handler,
        args=(handler, result_queue),
    )

    started_monotonic = time.monotonic()
    try:
        process.start()
        process.join(timeout_seconds)

        if process.is_alive():
            timeout_at_seconds = round(time.monotonic() - started_monotonic, 3)
            process.terminate()
            process.join(terminate_grace_seconds)

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

        result = _queue_result(result_queue, process, queue_grace_seconds)
        result["exitcode"] = process.exitcode
        result.setdefault("duration_seconds", round(time.monotonic() - started_monotonic, 3))
        return result
    finally:
        result_queue.close()
        result_queue.join_thread()
        process.close()
