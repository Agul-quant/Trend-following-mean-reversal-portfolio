#!/usr/bin/env python3
"""Accept QA-sealed private native packets; publish only derived forward returns.

No data acquisition or broker access. Missing packets remain awaiting data. A
failed/revised input is preserved in a new private attempt, never used to rewrite
previously accepted observations. See docs/paper_tracking.md for the contract.
"""

from __future__ import annotations

import argparse
import fcntl
from datetime import datetime, timezone
from hashlib import sha256
import json
import importlib.metadata
import platform
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trend_portfolio.paper_engine import (  # noqa: E402
    canonical,
    csv_bytes,
    digest,
    instant,
    load_freeze,
    replay,
    require,
)


def read(path):
    return json.loads(
        Path(path).read_text(),
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
    )


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def atomic(path, data):
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_previous(previous, freeze_sha, packet, existing_csv):
    """Both private input prefix and already published derived bytes are immutable."""
    require(
        previous["freeze_sha256"] == freeze_sha,
        "private state belongs to another freeze",
    )
    require(
        previous["warmup_sha256"] == digest(packet["warmup"]),
        "revised warmup quarantined; do not alter seed history",
    )
    old = previous["session_sha256"]
    new = [digest(row) for row in packet["sessions"]]
    require(
        len(new) >= len(old) and new[: len(old)] == old,
        "revised, removed or reordered accepted sessions quarantined",
    )
    require(
        sha256(existing_csv).hexdigest() == previous["public_daily_returns_sha256"],
        "public derived-return bytes no longer match the accepted receipt",
    )


def check_source_hashes(freeze):
    for name, expected in freeze["source_hashes"].items():
        path = ROOT / name
        require(
            path.resolve().is_relative_to(ROOT.resolve()) and not path.is_symlink(),
            "frozen source closure cannot escape the repository or use symlinks",
        )
        require(
            path.is_file() and sha256(path.read_bytes()).hexdigest() == expected,
            "frozen implementation/config changed: " + name,
        )
    for name, expected in freeze["runtime_versions"].items():
        actual = (
            platform.python_version()
            if name == "python"
            else importlib.metadata.version(name.replace("_", "-"))
        )
        require(actual == expected, "frozen paper runtime changed: " + name)


def bundle_targets(public, state_dir):
    return {
        "daily_returns.csv": public / "daily_returns.csv",
        "status.json": public / "status.json",
        "accepted.json": state_dir / "accepted.json",
    }


def apply_bundle(state_dir, public, journal, *, direction):
    """Recover a prepared commit or roll it back, never accepting unrelated edits."""
    attempt = state_dir / "attempts" / journal["attempt_id"]
    require(
        attempt.resolve().parent == (state_dir / "attempts").resolve(),
        "unsafe transaction attempt",
    )
    manifest_path = attempt / "transaction_manifest.json"
    require(
        sha256(manifest_path.read_bytes()).hexdigest() == journal["manifest_sha256"],
        "transaction manifest drift",
    )
    manifest = read(manifest_path)
    require(
        manifest["freeze_sha256"] == journal["freeze_sha256"],
        "transaction freeze mismatch",
    )
    targets = bundle_targets(public, state_dir)
    require(set(manifest["files"]) == set(targets), "transaction target set changed")
    prepared = {}
    for name, target in targets.items():
        require(not target.is_symlink(), "transaction output symlink rejected")
        bindings = manifest["files"][name]
        for side in ("before", "after"):
            expected = bindings[side]
            file = attempt / (side + "_" + name)
            require(
                expected is None or sha256(file.read_bytes()).hexdigest() == expected,
                "transaction bundle drift",
            )
        current = sha256(target.read_bytes()).hexdigest() if target.exists() else None
        require(
            current in (bindings["before"], bindings["after"]),
            "unrelated transaction target edits; manual recovery required",
        )
        prepared[name] = (
            None
            if bindings[direction] is None
            else (attempt / (direction + "_" + name)).read_bytes()
        )
    for name, target in targets.items():
        if prepared[name] is None:
            target.unlink(missing_ok=True)
        else:
            atomic(target, prepared[name])


def recover_transaction(state_dir, public, freeze_sha):
    path = state_dir / "transaction.json"
    if path.exists():
        journal = read(path)
        require(
            journal["freeze_sha256"] == freeze_sha,
            "unfinished transaction belongs to another freeze",
        )
        apply_bundle(state_dir, public, journal, direction="after")
        path.unlink()


def commit_bundle(state_dir, public, attempt, freeze_sha, after):
    """Write-ahead journal: exceptions roll back; a process crash rolls forward."""
    files = {}
    for name, target in bundle_targets(public, state_dir).items():
        before = target.read_bytes() if target.exists() else None
        if before is not None:
            (attempt / ("before_" + name)).write_bytes(before)
        (attempt / ("after_" + name)).write_bytes(after[name])
        files[name] = {
            "before": sha256(before).hexdigest() if before is not None else None,
            "after": sha256(after[name]).hexdigest(),
        }
    manifest = {
        "schema": "paper_publication_transaction_v1",
        "freeze_sha256": freeze_sha,
        "files": files,
    }
    write_new(attempt / "transaction_manifest.json", manifest)
    journal = {
        "attempt_id": attempt.name,
        "freeze_sha256": freeze_sha,
        "manifest_sha256": sha256(
            (attempt / "transaction_manifest.json").read_bytes()
        ).hexdigest(),
    }
    journal_path = state_dir / "transaction.json"
    require(not journal_path.exists(), "unfinished transaction must be recovered first")
    atomic(journal_path, canonical(journal))
    try:
        apply_bundle(state_dir, public, journal, direction="after")
    except Exception:
        # If disk failure also prevents rollback, retain the journal and fail
        # closed. The next locked run can complete the verified intended bundle.
        apply_bundle(state_dir, public, journal, direction="before")
        journal_path.unlink()
        raise
    journal_path.unlink()


def _run_locked(args, *, now, freeze_envelope, freeze, freeze_sha, public, state_dir):
    recover_transaction(state_dir, public, freeze_sha)
    if not Path(args.private_packet).is_file():
        status = {
            "schema": "forward_paper_tracking_status_v1",
            "freeze_sha256": freeze_sha,
            "status": "awaiting_qa_sealed_native_data",
            "start_session": freeze["start_session"],
            "accepted_sessions": 0,
            "performance_available": False,
            "checked_at_utc": now.isoformat(),
            "message": "No completed-session QA-sealed native packet is available; no paper returns have been invented.",
        }
        previous_path = state_dir / "accepted.json"
        if previous_path.is_file():
            prior = read(previous_path)
            require(
                prior["freeze_sha256"] == freeze_sha,
                "private state belongs to another freeze",
            )
            require(
                sha256((public / "daily_returns.csv").read_bytes()).hexdigest()
                == prior["public_daily_returns_sha256"],
                "public daily returns differ from the accepted receipt",
            )
            status.update(
                accepted_sessions=len(prior["session_sha256"]),
                performance_available=bool(prior["session_sha256"]),
                status="awaiting_next_qa_sealed_native_data",
            )
        if not args.status_only:
            public.mkdir(parents=True, exist_ok=True)
            atomic(
                public / "status.json",
                json.dumps(status, indent=2, sort_keys=True).encode() + b"\n",
            )
            if not (public / "daily_returns.csv").exists():
                atomic(public / "daily_returns.csv", csv_bytes([]))
        return status
    if args.status_only:
        return {
            "status": "packet_present_not_evaluated",
            "freeze_sha256": freeze_sha,
            "message": "Run without --status-only to validate and accept the packet.",
        }
    attempt = (
        state_dir / "attempts" / (now.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex)
    )
    attempt.mkdir(parents=True)
    try:
        packet_bytes = Path(args.private_packet).read_bytes()
        (attempt / "packet.json").write_bytes(packet_bytes)
        packet = read(attempt / "packet.json")
        previous_path = state_dir / "accepted.json"
        previous = read(previous_path) if previous_path.exists() else None
        public_csv = public / "daily_returns.csv"
        if previous is not None:
            validate_previous(previous, freeze_sha, packet, public_csv.read_bytes())
        else:
            require(
                not public_csv.exists() or public_csv.read_bytes() == csv_bytes([]),
                "unreceipted public observations cannot be adopted",
            )
        rows, private = replay(freeze_envelope, packet, now=now.isoformat())
        data = csv_bytes(rows)
        if previous is not None:
            old_count = len(previous["session_sha256"]) * 4
            require(
                csv_bytes(rows[:old_count]) == public_csv.read_bytes(),
                "previously published return prefix changed; quarantine without replacing it",
            )
        write_new(attempt / "private_account_state.json", private)
        receipt = {
            "schema": "forward_paper_packet_receipt_v1",
            "freeze_sha256": freeze_sha,
            "recorded_at_utc": now.isoformat(),
            "packet_sha256": sha256(packet_bytes).hexdigest(),
            "warmup_sha256": digest(packet["warmup"]),
            "session_sha256": [digest(row) for row in packet["sessions"]],
            "qa_sha256": digest(packet["qa"]),
            "public_daily_returns_sha256": sha256(data).hexdigest(),
            "previous_receipt_sha256": digest(previous) if previous else None,
            "attempt_id": attempt.name,
            "mode": "completed_day_modeled_paper_accounting_not_live_execution",
        }
        write_new(attempt / "accepted_receipt.json", receipt)
        public.mkdir(parents=True, exist_ok=True)
        status = {
            "schema": "forward_paper_tracking_status_v1",
            "freeze_sha256": freeze_sha,
            "status": "tracking_completed_sessions",
            "start_session": freeze["start_session"],
            "last_session": packet["sessions"][-1]["session"],
            "accepted_sessions": len(packet["sessions"]),
            "performance_available": True,
            "checked_at_utc": now.isoformat(),
            "observed_asof_utc": packet["created_at_utc"],
            "recorded_at_utc": now.isoformat(),
            "mode": receipt["mode"],
            "daily_returns_sha256": receipt["public_daily_returns_sha256"],
            "message": "Frozen-rule modeled paper observations; positions remain open and no terminal sale is imposed.",
        }
        commit_bundle(
            state_dir,
            public,
            attempt,
            freeze_sha,
            {
                "daily_returns.csv": data,
                "accepted.json": json.dumps(receipt, indent=2, sort_keys=True).encode()
                + b"\n",
                "status.json": json.dumps(status, indent=2, sort_keys=True).encode()
                + b"\n",
            },
        )
        return status
    except Exception as error:
        write_new(
            attempt / "rejected.json",
            {
                "recorded_at_utc": now.isoformat(),
                "status": "quarantined",
                "reason": str(error),
                "manual_crash_recovery_may_be_required": True,
            },
        )
        raise


def run(args, *, now=None):
    now = instant(now) if now is not None else datetime.now(timezone.utc)
    freeze_envelope = read(args.freeze)
    freeze, freeze_sha = load_freeze(freeze_envelope)
    check_source_hashes(freeze)
    public, state_dir = Path(args.output), Path(args.private_state)
    require(
        not public.is_symlink() and not state_dir.is_symlink(),
        "output/state directory symlinks are forbidden",
    )
    require(
        any(
            part in (".cache", "private")
            for part in Path(args.private_packet).resolve().parts
        ),
        "the raw packet must remain in an ignored .cache or private directory",
    )
    require(
        any(part in (".cache", "private") for part in state_dir.resolve().parts),
        "raw/private state must remain in an ignored .cache or private directory",
    )
    for filename in ("daily_returns.csv", "status.json"):
        require(
            not (public / filename).is_symlink(),
            "public output files cannot be symlinks",
        )
    state_dir.mkdir(parents=True, exist_ok=True)
    if args.status_only:
        require(
            not (state_dir / "transaction.json").exists(),
            "unfinished transaction requires a non-status-only recovery run",
        )
    # Advisory lock automatically releases after a crash. Its persistent private
    # lock file is not evidence that an updater is currently running.
    with (state_dir / "update.lock").open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "another paper updater holds the private advisory lock"
            ) from error
        lock.seek(0)
        lock.truncate()
        lock.write(f"{os.getpid()} {now.isoformat()}\n")
        lock.flush()
        return _run_locked(
            args,
            now=now,
            freeze_envelope=freeze_envelope,
            freeze=freeze,
            freeze_sha=freeze_sha,
            public=public,
            state_dir=state_dir,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freeze", type=Path, default=ROOT / "configs/paper_portfolio_freeze.json"
    )
    parser.add_argument(
        "--private-packet",
        type=Path,
        default=ROOT / ".cache/paper_tracking/input/packet.json",
    )
    parser.add_argument(
        "--private-state", type=Path, default=ROOT / ".cache/paper_tracking/state"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports/paper_tracking")
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(
            "Paper update refused; inspect the private rejection/journal before retrying: "
            + str(error),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
