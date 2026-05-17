import os
import uuid
from datetime import datetime, timedelta, timezone

from supabase import create_client


LOCK_TABLE = "runtime_global_lock"
LOCK_ID = 1
DEFAULT_TTL_SECONDS = 420


def _now_utc():
    return datetime.now(timezone.utc)


def _owner():
    raw_owner = str(os.getenv("TITAN_RUNTIME_OWNER") or "UNKNOWN").strip() or "UNKNOWN"
    return "".join(ch for ch in raw_owner if ch.isalnum() or ch in {"_", "-"}) or "UNKNOWN"


def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("missing Supabase runtime lock credentials")
    return create_client(url, key)


def _parse_timestamp(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lock_is_available(row, owner, now):
    if not row:
        return True
    existing_owner = str(row.get("owner") or "").strip()
    expires_at = _parse_timestamp(row.get("expires_at"))
    return not existing_owner or (expires_at is not None and expires_at <= now)


def _claim_filter(now):
    return (
        "owner.is.null,"
        f"expires_at.lte.{now.isoformat()}"
    )


def acquire_global_runtime_lock(mode="LIVE", ttl_seconds=DEFAULT_TTL_SECONDS):
    owner = _owner()
    run_id = uuid.uuid4().hex
    now = _now_utc()
    expires_at = now + timedelta(seconds=int(ttl_seconds or DEFAULT_TTL_SECONDS))

    try:
        client = _client()
        result = (
            client.table(LOCK_TABLE)
            .select("id,owner,run_id,heartbeat,expires_at,mode")
            .eq("id", LOCK_ID)
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]

        if not _lock_is_available(row, owner, now):
            print(
                "GLOBAL_LOCK_REJECTED "
                f"owner={owner} run_id={run_id} "
                f"held_by={row.get('owner')} held_run_id={row.get('run_id')} "
                f"expires_at={row.get('expires_at')}"
            )
            return {
                "acquired": False,
                "owner": owner,
                "run_id": run_id,
                "held_by": row.get("owner"),
                "held_run_id": row.get("run_id"),
                "reason": "HELD_BY_OTHER",
            }

        payload = {
            "id": LOCK_ID,
            "owner": owner,
            "run_id": run_id,
            "heartbeat": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "mode": mode,
        }

        if row:
            claim_result = (
                client.table(LOCK_TABLE)
                .update(payload)
                .eq("id", LOCK_ID)
                .or_(_claim_filter(now))
                .execute()
            )
            if not claim_result.data:
                latest = (
                    client.table(LOCK_TABLE)
                    .select("id,owner,run_id,expires_at,mode")
                    .eq("id", LOCK_ID)
                    .limit(1)
                    .execute()
                )
                latest_row = (latest.data or [None])[0]
                print(
                    "GLOBAL_LOCK_REJECTED "
                    f"owner={owner} run_id={run_id} "
                    f"held_by={latest_row.get('owner') if latest_row else None} "
                    f"held_run_id={latest_row.get('run_id') if latest_row else None} "
                    f"expires_at={latest_row.get('expires_at') if latest_row else None}"
                )
                return {
                    "acquired": False,
                    "owner": owner,
                    "run_id": run_id,
                    "held_by": latest_row.get("owner") if latest_row else None,
                    "held_run_id": latest_row.get("run_id") if latest_row else None,
                    "reason": "HELD_BY_OTHER",
                }
        else:
            client.table(LOCK_TABLE).insert(payload).execute()

        verify = (
            client.table(LOCK_TABLE)
            .select("id,owner,run_id,expires_at,mode")
            .eq("id", LOCK_ID)
            .limit(1)
            .execute()
        )
        verified_row = (verify.data or [None])[0]
        if (
            not verified_row
            or str(verified_row.get("owner") or "") != owner
            or str(verified_row.get("run_id") or "") != run_id
        ):
            print(
                "GLOBAL_LOCK_REJECTED "
                f"owner={owner} run_id={run_id} reason=VERIFY_FAILED "
                f"held_by={verified_row.get('owner') if verified_row else None} "
                f"held_run_id={verified_row.get('run_id') if verified_row else None}"
            )
            return {
                "acquired": False,
                "owner": owner,
                "run_id": run_id,
                "held_by": verified_row.get("owner") if verified_row else None,
                "held_run_id": verified_row.get("run_id") if verified_row else None,
                "reason": "VERIFY_FAILED",
            }

        print(
            "GLOBAL_LOCK_ACQUIRED "
            f"owner={owner} run_id={run_id} expires_at={verified_row.get('expires_at')}"
        )
        return {
            "acquired": True,
            "owner": owner,
            "run_id": run_id,
            "expires_at": verified_row.get("expires_at"),
            "reason": "ACQUIRED",
        }

    except Exception as exc:
        print(f"GLOBAL_LOCK_ERROR reason={exc}")
        return {
            "acquired": False,
            "owner": owner,
            "run_id": run_id,
            "reason": "ERROR",
            "error": str(exc),
        }


def release_global_runtime_lock(owner=None, run_id=None):
    owner = str(owner or _owner()).strip() or "UNKNOWN"
    run_id = str(run_id or "").strip()
    now = _now_utc()

    if not run_id:
        print(f"GLOBAL_LOCK_RELEASE_REJECTED owner={owner} run_id= reason=MISSING_RUN_ID")
        return False

    try:
        client = _client()
        result = (
            client.table(LOCK_TABLE)
            .select("id,owner,run_id")
            .eq("id", LOCK_ID)
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]
        if (
            not row
            or str(row.get("owner") or "") != owner
            or str(row.get("run_id") or "") != run_id
        ):
            print(
                "GLOBAL_LOCK_RELEASE_REJECTED "
                f"owner={owner} run_id={run_id} "
                f"held_by={row.get('owner') if row else None} "
                f"held_run_id={row.get('run_id') if row else None}"
            )
            return False

        client.table(LOCK_TABLE).update(
            {
                "owner": None,
                "run_id": None,
                "heartbeat": now.isoformat(),
                "expires_at": now.isoformat(),
                "mode": "IDLE",
            }
        ).eq("id", LOCK_ID).execute()
        print(f"GLOBAL_LOCK_RELEASED owner={owner} run_id={run_id}")
        return True

    except Exception as exc:
        print(f"GLOBAL_LOCK_ERROR reason={exc}")
        return False
