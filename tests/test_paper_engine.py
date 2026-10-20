"""Generated prices and time-only calendars only; never load a market capture."""

from argparse import Namespace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import importlib.metadata
import platform
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from trend_portfolio import paper_engine as paper


@pytest.fixture(scope="module")
def base():
    freeze = {
        "frozen_at_utc": "2026-10-20T17:00:00+00:00",
        "start_session": "2026-10-21",
        "start_open_utc": "2026-10-21T13:30:00+00:00",
        "symbols": paper.SYMBOLS,
        "initial_weights": paper.WEIGHTS,
        "primary_frequency": "none",
        "initial_cash": 1000,
        "commission_bps_each_way": 1,
        "slippage_bps_each_way": paper.COSTS,
        "cash_nominal_rate": 0.03,
        "cash_day_count": "ACT/365",
        "source_hashes": {
            p: sha256((Path(__file__).parents[1] / p).read_bytes()).hexdigest()
            for p in paper.REQUIRED_SOURCE_FILES
        },
        "runtime_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "exchange_calendars": importlib.metadata.version("exchange_calendars"),
        },
    }
    envelope = {
        "schema": "forward_paper_portfolio_freeze_v1",
        "payload": freeze,
        "payload_sha256": paper.digest(freeze),
    }
    cal = paper.calendar_rows("2015-01-01", "2026-10-22")
    warmup, sessions = [], []
    for day, (op, close) in cal.items():
        mark = (
            datetime.fromisoformat(day)
            .replace(hour=17, tzinfo=paper.NY)
            .astimezone(timezone.utc)
        )
        row = {
            "session": day,
            "available_at_utc": mark.isoformat(),
            "symbols": {
                s: {"close": 100.0, "split": 1.0, "dividend": 0.0}
                for s in paper.SYMBOLS
            },
        }
        if day < "2026-10-21":
            warmup.append(row)
            continue
        row.update(market_open_utc=op.isoformat(), market_close_utc=close.isoformat())
        for symbol in paper.SYMBOLS:
            row["symbols"][symbol]["bars"] = [
                {
                    "start": (op + timedelta(minutes=30 * i)).isoformat(),
                    "end": (op + timedelta(minutes=30 * (i + 1))).isoformat(),
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1000.0,
                }
                for i in range(int((close - op).total_seconds() // 1800))
            ]
        sessions.append(row)
    packet = {
        "schema": "forward_paper_native_packet_v1",
        "freeze_sha256": envelope["payload_sha256"],
        "created_at_utc": "2026-10-22T22:00:00+00:00",
        "qa": {
            "price_basis": "native_raw",
            "adjusted": False,
            "extended_hours": False,
            "interval_minutes": 30,
            "checks": {
                **dict.fromkeys(paper.QA_CHECKS, "passed"),
                "available_15_to_30": "not_available",
            },
            "evidence_sha256": ["a" * 64],
            "attested_at_utc": "2026-10-22T21:30:00+00:00",
        },
        "warmup": warmup,
        "sessions": sessions,
    }
    return envelope, packet


def run(base, packet=None):
    return paper.replay(base[0], packet or base[1], now="2026-10-23T00:00:00+00:00")


def priced_day(packet, day, symbol, prices):
    row = packet["sessions"][day]["symbols"][symbol]
    for bar, price in zip(row["bars"], prices):
        for key in ("open", "high", "low", "close"):
            bar[key] = float(price)
    row["close"] = float(prices[-1])


def test_flat_cash_fresh_1000_four_costs_no_phantom_wealth(base):
    rows, private = run(base)
    assert len(rows) == 8
    for row in rows:
        assert row["portfolio_return"] == pytest.approx(row["cash_return"], abs=3e-15)
    assert not any(private["logical_long"])
    for account in private["accounts"]:
        assert account["ledger"] == []
        assert sum(account["cash"]) == pytest.approx(private["cash_reference"])
        assert (
            account["qqq_shares"] > 0
        )  # Benchmark holds, without artificial terminal sell.


def test_seven_checks_then_next_bar_open_paid_entry_and_no_terminal_close(base):
    packet = deepcopy(base[1])
    priced_day(packet, 0, "QQQ", [110] * 13)
    priced_day(packet, 1, "QQQ", [111] * 13)
    rows, private = run(base, packet)
    assert private["logical_long"][2]
    for account in private["accounts"]:
        orders = [r for r in account["ledger"] if r["symbol"] == "QQQ"]
        assert len(orders) == 1 and orders[0]["side"] == 1
        assert orders[0]["timestamp"] == "2026-10-21T17:00:00+00:00"  # 13:00 NY
        assert orders[0]["decision_at"] == "2026-10-21T17:00:00+00:00"
        assert paper.instant(orders[0]["decision_bar_start"]) < paper.instant(
            orders[0]["timestamp"]
        )
        assert account["shares"][2] > 0
        assert orders[0]["commission"] > 0
        assert all(r["reason"] != "terminal_liquidation" for r in account["ledger"])
    assert (
        rows[0]["portfolio_return"] > rows[3]["portfolio_return"]
    )  # Costs really differ.


def test_confirmation_streak_and_pending_order_cross_sessions(base):
    packet = deepcopy(base[1])
    priced_day(
        packet, 0, "QQQ", [100] * 6 + [110] * 7
    )  # seventh check at final close; pending overnight.
    priced_day(packet, 1, "QQQ", [111] * 13)
    one = deepcopy(packet)
    one["sessions"] = one["sessions"][:1]
    _, first = run(base, one)
    assert first["pending"][2][0] == 1 and first["entry_streaks"][2] == 7
    rows, full = run(base, packet)
    for account in full["accounts"]:
        orders = [r for r in account["ledger"] if r["symbol"] == "QQQ"]
        assert orders[0]["timestamp"] == "2026-10-22T13:30:00+00:00"
        assert orders[0]["decision_at"] == "2026-10-21T20:00:00+00:00"
    assert paper.csv_bytes(rows[:4]) == paper.csv_bytes(run(base, one)[0])


def test_daily_features_preview_does_not_advance_ema_rsi_or_history():
    for symbol in paper.SYMBOLS:
        state = paper.FeatureState(symbol)
        for day in range(300):
            state.finalize(100 + day * 0.01, 1, 0)
        before = (
            state.count,
            state.ema.copy(),
            state.gain,
            state.loss,
            list(state.history),
        )
        a, b = state.preview(110, 1, 0), state.preview(110, 1, 0)
        assert a == b
        assert before == (
            state.count,
            state.ema,
            state.gain,
            state.loss,
            list(state.history),
        )


def test_total_return_feature_split_and_dividend_match_economic_flat_value():
    state = paper.FeatureState("GDX")
    for _ in range(300):
        state.finalize(100, 1, 0)
    assert state.preview(49, 2, 1) == (False, False)
    state.finalize(49, 2, 1)
    assert state.prior_index == 100
    assert state.prior_raw == 49


def test_zscore_uses_sample_std_not_population_and_constant_is_undefined():
    state = paper.FeatureState("GDX")
    for _ in range(300):
        state.finalize(100.2, 1, 0)
    assert state.preview(100.2, 1, 0) == (False, False)
    assert state.preview(90, 1, 0)[0]


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda p: p["qa"].update(adjusted=True), "native raw"),
        (lambda p: p["qa"]["checks"].update(price_units="failed"), "reconciliation"),
        (lambda p: p["qa"].update(evidence_sha256=[]), "evidence hashes"),
        (
            lambda p: p.update(created_at_utc="2026-10-24T00:00:00+00:00"),
            "future packet",
        ),
        (lambda p: p["sessions"][0]["symbols"]["GDX"]["bars"].pop(), "half-hour"),
        (
            lambda p: p["sessions"][0].update(
                market_open_utc="2026-10-21T14:30:00+00:00"
            ),
            "XNYS",
        ),
        (lambda p: p["sessions"][0]["symbols"]["QQQ"].update(close=-1), "positive"),
        (
            lambda p: p["sessions"][0]["symbols"]["QQQ"]["bars"][0].update(high=1),
            "envelope",
        ),
        (lambda p: p["sessions"].pop(0), "first paper"),
        (lambda p: p["warmup"].pop(0), "2015 feature"),
    ],
)
def test_invalid_or_future_native_packet_blocks(base, mutation, match):
    packet = deepcopy(base[1])
    mutation(packet)
    with pytest.raises(ValueError, match=match):
        run(base, packet)


def test_future_daily_mark_not_even_if_user_claims_complete(base):
    with pytest.raises(ValueError, match="future QA|future packet|completed"):
        paper.replay(base[0], base[1], now="2026-10-21T19:00:00+00:00")


def test_freeze_checksum_and_implementation_policy_cannot_change(base):
    envelope = deepcopy(base[0])
    envelope["payload"]["primary_frequency"] = "weekly"
    with pytest.raises(ValueError, match="checksum"):
        paper.load_freeze(envelope)
    envelope["payload_sha256"] = paper.digest(envelope["payload"])
    with pytest.raises(ValueError, match="no-rebalancing"):
        paper.load_freeze(envelope)


def cli_module():
    path = Path(__file__).parents[1] / "scripts/run_paper_tracker.py"
    spec = importlib.util.spec_from_file_location("paper_tracker_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_data_waits_truthfully_no_fake_return_or_performance(base, tmp_path):
    module = cli_module()
    freeze = tmp_path / "freeze.json"
    freeze.write_bytes(paper.canonical(base[0]))
    output = tmp_path / "public"
    args = Namespace(
        freeze=freeze,
        private_packet=tmp_path / ".cache/missing.json",
        private_state=tmp_path / ".cache/state",
        output=output,
        status_only=False,
    )
    status = module.run(args, now="2026-10-20T18:00:00+00:00")
    assert not status["performance_available"] and status["accepted_sessions"] == 0
    assert (output / "daily_returns.csv").read_bytes() == paper.csv_bytes([])
    assert ".cache" not in json.dumps(status)


def test_append_only_prefix_revisions_quarantined_and_no_raw_public_data(
    base, tmp_path
):
    module = cli_module()
    freeze, packet = deepcopy(base)
    path = tmp_path / ".cache/packet.json"
    path.parent.mkdir()
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_bytes(paper.canonical(freeze))
    args = Namespace(
        freeze=freeze_path,
        private_packet=path,
        private_state=tmp_path / ".cache/state",
        output=tmp_path / "public",
        status_only=False,
    )
    first = deepcopy(packet)
    first["sessions"] = first["sessions"][:1]
    path.write_bytes(paper.canonical(first))
    module.run(args, now="2026-10-23T00:00:00+00:00")
    prefix = (args.output / "daily_returns.csv").read_bytes()
    path.write_bytes(paper.canonical(packet))
    status = module.run(args, now="2026-10-23T00:00:01+00:00")
    assert status["accepted_sessions"] == 2
    accepted = (args.output / "daily_returns.csv").read_bytes()
    assert accepted.startswith(prefix)
    assert len(accepted.decode().splitlines()) == 9
    module.run(
        args, now="2026-10-23T00:00:02+00:00"
    )  # idempotent rows, new auditable receipt.
    assert (args.output / "daily_returns.csv").read_bytes() == accepted
    packet["sessions"][0]["symbols"]["GDX"]["close"] += 0.01
    path.write_bytes(paper.canonical(packet))
    with pytest.raises(ValueError, match="quarantined"):
        module.run(args, now="2026-10-23T00:00:03+00:00")
    assert (args.output / "daily_returns.csv").read_bytes() == accepted
    assert len(list((args.private_state / "attempts").glob("*/rejected.json"))) == 1
    assert not (args.private_state / "transaction.json").exists()
    for file in args.output.iterdir():
        public_text = file.read_text()
        assert (
            "raw_price" not in public_text
            and "quantity" not in public_text
            and "bars" not in public_text
        )
    columns = accepted.decode().splitlines()[0].split(",")
    assert columns == paper.PUBLIC_FIELDS


def test_tampered_public_returns_refused_before_new_acceptance(base, tmp_path):
    module = cli_module()
    previous = {
        "freeze_sha256": base[0]["payload_sha256"],
        "warmup_sha256": paper.digest(base[1]["warmup"]),
        "session_sha256": [paper.digest(r) for r in base[1]["sessions"]],
        "public_daily_returns_sha256": "0" * 64,
    }
    with pytest.raises(ValueError, match="derived-return bytes"):
        module.validate_previous(
            previous, base[0]["payload_sha256"], base[1], b"tampered"
        )


def test_transaction_exception_rolls_back_all_public_and_private_commit_files(
    tmp_path, monkeypatch
):
    module = cli_module()
    state, public = tmp_path / ".cache/state", tmp_path / "public"
    attempt = state / "attempts/attempt-1"
    attempt.mkdir(parents=True)
    public.mkdir()
    before = {
        name: ("before-" + name).encode()
        for name in module.bundle_targets(public, state)
    }
    after = {name: ("after-" + name).encode() for name in before}
    for name, target in module.bundle_targets(public, state).items():
        target.write_bytes(before[name])
    original, calls = module.atomic, [0]

    def fail_once(path, data):
        calls[0] += 1
        if calls[0] == 3:
            raise OSError("synthetic failure after CSV but before accepted state")
        return original(path, data)

    monkeypatch.setattr(module, "atomic", fail_once)
    with pytest.raises(OSError, match="synthetic failure"):
        module.commit_bundle(state, public, attempt, "f" * 64, after)
    assert not (state / "transaction.json").exists()
    for name, target in module.bundle_targets(public, state).items():
        assert target.read_bytes() == before[name]


def test_crash_journal_rolls_forward_known_verified_bundle_without_repricing(
    tmp_path, monkeypatch
):
    module = cli_module()
    state, public = tmp_path / ".cache/state", tmp_path / "public"
    attempt = state / "attempts/attempt-1"
    attempt.mkdir(parents=True)
    public.mkdir()
    before = {
        name: ("before-" + name).encode()
        for name in module.bundle_targets(public, state)
    }
    after = {name: ("after-" + name).encode() for name in before}
    for name, target in module.bundle_targets(public, state).items():
        target.write_bytes(before[name])
    original, calls = module.atomic, [0]

    def crash_once(path, data):
        calls[0] += 1
        if calls[0] == 3:
            raise SystemExit("synthetic process death")
        return original(path, data)

    monkeypatch.setattr(module, "atomic", crash_once)
    with pytest.raises(SystemExit):
        module.commit_bundle(state, public, attempt, "f" * 64, after)
    assert (state / "transaction.json").exists()
    monkeypatch.setattr(module, "atomic", original)
    module.recover_transaction(state, public, "f" * 64)
    assert not (state / "transaction.json").exists()
    for name, target in module.bundle_targets(public, state).items():
        assert target.read_bytes() == after[name]


def test_unrelated_edit_during_crash_recovery_fails_closed(tmp_path):
    module = cli_module()
    state, public = tmp_path / ".cache/state", tmp_path / "public"
    attempt = state / "attempts/attempt-1"
    attempt.mkdir(parents=True)
    public.mkdir()
    files = {}
    for name, target in module.bundle_targets(public, state).items():
        before, after = b"before", b"after"
        (attempt / ("before_" + name)).write_bytes(before)
        (attempt / ("after_" + name)).write_bytes(after)
        target.write_bytes(b"unrelated edit")
        files[name] = {
            "before": sha256(before).hexdigest(),
            "after": sha256(after).hexdigest(),
        }
    module.write_new(
        attempt / "transaction_manifest.json",
        {"freeze_sha256": "f" * 64, "files": files},
    )
    journal = {
        "freeze_sha256": "f" * 64,
        "attempt_id": attempt.name,
        "manifest_sha256": sha256(
            (attempt / "transaction_manifest.json").read_bytes()
        ).hexdigest(),
    }
    (state / "transaction.json").write_bytes(paper.canonical(journal))
    with pytest.raises(ValueError, match="unrelated transaction"):
        module.recover_transaction(state, public, "f" * 64)
    assert (state / "transaction.json").exists()
    assert (public / "daily_returns.csv").read_bytes() == b"unrelated edit"
