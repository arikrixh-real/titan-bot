import multiprocessing
import queue
import traceback


def _run_handler(handler, result_queue):
    try:
        handler()
        result_queue.put({"status": "ok"})
    except BaseException as exc:
        result_queue.put(
            {
                "status": "error",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
        )


def run_with_timeout(handler, timeout_seconds):
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

    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(5)

        if process.is_alive():
            process.kill()
            process.join(5)

        return {
            "status": "timeout",
            "timeout_seconds": timeout_seconds,
            "exitcode": process.exitcode,
        }

    try:
        result = result_queue.get_nowait()
    except queue.Empty:
        if process.exitcode == 0:
            result = {"status": "ok"}
        else:
            result = {
                "status": "error",
                "error": f"handler exited without result exitcode={process.exitcode}",
                "traceback": "",
            }

    result["exitcode"] = process.exitcode
    return result
