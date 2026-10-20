"""Forward-only, no-rebalancing paper replay over explicitly QA-sealed private inputs.

No downloader, credential access, live orders, optimizer, or terminal liquidation.
The packet is an input contract, not automatic proof that vendor data passed QA.
All source OHLCV, actions, positions, and the order ledger stay in private state.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import csv
import io
import json
from math import fsum, isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo("America/New_York")
SYMBOLS = ["GDX", "FXI", "QQQ", "UNG", "FDN"]
WEIGHTS = {
    "GDX": 0.2905130826010515,
    "FXI": 0.2799197437112525,
    "QQQ": 0.06304492619579012,
    "UNG": 0.26729328450466966,
    "FDN": 0.0992289629872361,
}
COSTS = [1, 3, 10, 25]
PUBLIC_FIELDS = [
    "session",
    "timestamp",
    "slippage_bps",
    "portfolio_return",
    "cash_return",
    "qqq_bh_return",
]
REQUIRED_SOURCE_FILES = {
    "src/trend_portfolio/paper_engine.py",
    "scripts/run_paper_tracker.py",
    "configs/selected_etf_strategies.json",
    "configs/final_cap_rebalancing.json",
}
QA_CHECKS = (
    "calendar",
    "coverage",
    "price_units",
    "corporate_actions",
    "native_overlap",
    "daily_anchors",
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def instant(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("explicitly timezone-aware timestamp required")
    return stamp.astimezone(timezone.utc)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def positive(value, label):
    require(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
        and value > 0,
        label + " must be finite and positive",
    )
    return float(value)


def load_freeze(value):
    envelope = (
        json.loads(Path(value).read_text()) if isinstance(value, (str, Path)) else value
    )
    require(
        envelope.get("schema") == "forward_paper_portfolio_freeze_v1",
        "unknown paper freeze schema",
    )
    payload = envelope["payload"]
    require(
        digest(payload) == envelope.get("payload_sha256"),
        "paper freeze checksum mismatch",
    )
    require(
        payload["symbols"] == SYMBOLS and payload["initial_weights"] == WEIGHTS,
        "paper freeze must retain the exact five symbols and saved weights",
    )
    require(
        payload["primary_frequency"] == "none",
        "this engine implements no-rebalancing only",
    )
    require(
        payload["initial_cash"] == 1000
        and payload["commission_bps_each_way"] == 1
        and payload["slippage_bps_each_way"] == COSTS
        and payload["cash_nominal_rate"] == 0.03
        and payload["cash_day_count"] == "ACT/365",
        "paper accounting policy changed",
    )
    require(
        instant(payload["frozen_at_utc"]) < instant(payload["start_open_utc"]),
        "freeze must precede the first future session open",
    )
    sources = payload.get("source_hashes", {})
    require(
        isinstance(sources, dict) and REQUIRED_SOURCE_FILES <= set(sources),
        "paper freeze must bind the implementation and exact strategy/policy source closure",
    )
    for name, value in sources.items():
        require(
            not Path(name).is_absolute()
            and ".." not in Path(name).parts
            and isinstance(value, str)
            and len(value) == 64
            and all(c in "0123456789abcdef" for c in value),
            "source bindings require safe repository-relative paths and SHA256 bytes",
        )
    runtime = payload.get("runtime_versions", {})
    require(
        isinstance(runtime, dict)
        and {"python", "numpy", "exchange_calendars"} <= set(runtime)
        and all(isinstance(v, str) and v for v in runtime.values()),
        "pinned paper runtime versions are required",
    )
    return payload, envelope["payload_sha256"]


def calendar_rows(start, end):
    """Time-only exchange calendar; never queries prices or future outcomes."""
    import exchange_calendars as xc

    cal = xc.get_calendar("XNYS", start=start, end=end)
    rows = {}
    for date, row in cal.schedule.iterrows():
        day = date.strftime("%Y-%m-%d")
        rows[day] = (
            instant(row["open"].isoformat()),
            instant(row["close"].isoformat()),
        )
    return rows


class FeatureState:
    """Same daily EMA, sample-Z-score and Wilder-RSI preview recursions as the study."""

    def __init__(self, symbol):
        self.symbol = symbol
        self.count = 0
        self.history = deque(maxlen=50)
        self.ema = {p: None for p in (50, 100, 200)}
        self.previous = None
        self.gain = self.loss = 0.0
        self.prior_raw = None
        self.prior_index = 100.0

    def _transition(self, value):
        count = self.count + 1
        ema = {
            p: value if old is None else old + 2 / (p + 1) * (value - old)
            for p, old in self.ema.items()
        }
        gain, loss = self.gain, self.loss
        if self.previous is not None:
            change = value - self.previous
            gain_change, loss_change = max(change, 0), max(-change, 0)
            if self.count - 1 < 14:
                gain, loss = gain + gain_change, loss + loss_change
                if self.count == 14:
                    gain, loss = gain / 14, loss / 14
            else:
                gain, loss = (
                    gain + (gain_change - gain) / 14,
                    loss + (loss_change - loss) / 14,
                )
        if self.symbol in ("QQQ", "FDN"):
            period = 200 if self.symbol == "QQQ" else 100
            entry = count >= period and value - ema[50] > 0 and value - ema[period] > 0
            exit_ = count >= period and not value - ema[period] > 0
        elif self.symbol in ("GDX", "FXI"):
            period = 20 if self.symbol == "GDX" else 50
            z = float("nan")
            if count >= period:
                window = np.asarray(list(self.history)[-(period - 1) :] + [value])
                offsets = window - value
                std = float(np.std(offsets, ddof=1))
                if np.ptp(offsets) > 0 and std > 0:
                    z = -float(np.mean(offsets)) / std
            entry, exit_ = (
                isfinite(z) and z <= -2,
                isfinite(z) and z >= (0 if self.symbol == "GDX" else 0.5),
            )
        else:
            rsi = float("nan")
            if self.previous is not None and self.count >= 14:
                rsi = (
                    50
                    if gain == loss == 0
                    else 100
                    if loss == 0
                    else 0
                    if gain == 0
                    else 100 - 100 / (1 + gain / loss)
                )
            entry, exit_ = isfinite(rsi) and rsi <= 30, isfinite(rsi) and rsi >= 50
        return bool(entry), bool(exit_), ema, gain, loss

    def preview(self, raw, split, dividend):
        require(self.prior_raw is not None, "feature warmup missing")
        value = self.prior_index * split * (raw + dividend) / self.prior_raw
        return self._transition(positive(value, "provisional signal index"))[:2]

    def finalize(self, raw, split, dividend):
        value = (
            100.0
            if self.prior_raw is None
            else self.prior_index * split * (raw + dividend) / self.prior_raw
        )
        _, _, self.ema, self.gain, self.loss = self._transition(
            positive(value, "daily signal index")
        )
        self.history.append(value)
        self.previous, self.prior_index, self.prior_raw = value, value, raw
        self.count += 1


def _action(row):
    close, split = (
        positive(row["close"], "raw daily close"),
        positive(row["split"], "split"),
    )
    div = row["dividend"]
    require(
        not isinstance(div, bool)
        and isinstance(div, (int, float))
        and isfinite(div)
        and div >= 0,
        "nonnegative finite cash dividend required",
    )
    return close, split, float(div)


def validate_packet(packet, freeze, freeze_sha, now):
    """Reject incomplete grids, future/backdated starts, and unsupported price units."""
    require(
        packet.get("schema") == "forward_paper_native_packet_v1",
        "unknown private native packet schema",
    )
    require(
        packet.get("freeze_sha256") == freeze_sha, "packet belongs to another freeze"
    )
    qa = packet["qa"]
    require(
        qa.get("price_basis") == "native_raw"
        and qa.get("adjusted") is False
        and qa.get("extended_hours") is False
        and qa.get("interval_minutes") == 30,
        "certified native raw regular-session 30-minute prices required",
    )
    require(
        all(qa.get("checks", {}).get(key) == "passed" for key in QA_CHECKS),
        "strict source reconciliation evidence is incomplete",
    )
    require(
        qa["checks"].get("available_15_to_30") in ("passed", "not_available"),
        "15-to-30 evidence status missing",
    )
    require(
        isinstance(qa.get("evidence_sha256"), list)
        and qa["evidence_sha256"]
        and all(
            isinstance(h, str)
            and len(h) == 64
            and all(c in "0123456789abcdef" for c in h)
            for h in qa["evidence_sha256"]
        ),
        "private QA evidence hashes required",
    )
    require(instant(qa["attested_at_utc"]) <= now, "future QA attestation rejected")
    require(instant(packet["created_at_utc"]) <= now, "future packet creation rejected")
    warmup, sessions = packet["warmup"], packet["sessions"]
    require(
        len(warmup) >= 295 and sessions,
        "at least 295 completed daily seed rows and a complete future session required",
    )
    dates = [r["session"] for r in warmup + sessions]
    require(
        dates == sorted(set(dates)),
        "daily sessions must be unique and strictly increasing",
    )
    require(
        warmup[0]["session"] == "2015-01-02",
        "the unchanged available 2015 feature seed is required",
    )
    require(
        sessions[0]["session"] == freeze["start_session"],
        "no missing or backdated first paper session",
    )
    cal = calendar_rows("2015-01-01", dates[-1])
    require(
        dates == list(cal),
        "warmup and paper data must cover every actual XNYS session from 2015",
    )
    require(
        cal[freeze["start_session"]][0] == instant(freeze["start_open_utc"]),
        "frozen start disagrees with XNYS",
    )
    for row_index, row in enumerate(warmup + sessions):
        day = row["session"]
        require(
            set(row["symbols"]) == set(SYMBOLS),
            "each session requires exactly the frozen five ETFs",
        )
        mark = (
            datetime.fromisoformat(day)
            .replace(hour=17, tzinfo=NY)
            .astimezone(timezone.utc)
        )
        require(
            mark <= now and instant(row["available_at_utc"]) == mark,
            "daily data require completed 17 New York availability",
        )
        require(
            instant(packet["created_at_utc"]) >= mark,
            "packet predates one of its daily marks",
        )
        for symbol in SYMBOLS:
            _action(row["symbols"][symbol])
        if row_index < len(warmup):
            continue
        op, close = cal[day]
        require(
            instant(row["market_open_utc"]) == op
            and instant(row["market_close_utc"]) == close,
            "native session clock disagrees with XNYS holiday/DST/early-close schedule",
        )
        for symbol in SYMBOLS:
            bars = row["symbols"][symbol]["bars"]
            expected = int((close - op).total_seconds() // 1800)
            require(len(bars) == expected, "missing or duplicate native half-hour bars")
            for i, bar in enumerate(bars):
                require(
                    instant(bar["start"]) == op + timedelta(minutes=30 * i)
                    and instant(bar["end"]) == op + timedelta(minutes=30 * (i + 1)),
                    "native bar grid is incomplete or reordered",
                )
                bar_open, bar_high, bar_low, bar_close = [
                    positive(bar[k], "native OHLC")
                    for k in ("open", "high", "low", "close")
                ]
                require(
                    bar_low
                    <= min(bar_open, bar_close)
                    <= max(bar_open, bar_close)
                    <= bar_high,
                    "native OHLC envelope invalid",
                )
                require(
                    not isinstance(bar["volume"], bool)
                    and isfinite(bar["volume"])
                    and bar["volume"] >= 0,
                    "finite nonnegative native volume required",
                )
    require(
        instant(qa["attested_at_utc"]) >= instant(sessions[-1]["available_at_utc"])
        and instant(qa["attested_at_utc"]) <= instant(packet["created_at_utc"]),
        "QA must follow the last complete daily mark and precede packet creation",
    )
    return warmup, sessions, cal


def replay(freeze_envelope, packet, *, now=None):
    """Recompute a growing forward prefix, without closing positions at the cutoff.

    Prefix immutability is enforced by the CLI before any new receipt is accepted.
    The completed-day replay is modeled paper accounting, not real-time fills.
    """
    freeze, freeze_sha = load_freeze(freeze_envelope)
    now = instant(now) if now is not None else datetime.now(timezone.utc)
    warmup, sessions, cal = validate_packet(packet, freeze, freeze_sha, now)
    features = {s: FeatureState(s) for s in SYMBOLS}
    for row in warmup:
        for symbol in SYMBOLS:
            features[symbol].finalize(*_action(row["symbols"][symbol]))
    accounts = []
    for cost in COSTS:
        accounts.append(
            {
                "slippage_bps": cost,
                "cash": np.array([WEIGHTS[s] * 1000 for s in SYMBOLS]),
                "shares": np.zeros(5),
                "dividend_cash": np.zeros(5),
                "qqq_cash": 1000.0,
                "qqq_shares": 0.0,
                "qqq_dividend_cash": 0.0,
                "previous_equity": 1000.0,
                "previous_qqq": 1000.0,
                "ledger": [],
            }
        )
    logical = np.zeros(5, bool)
    entry_count, exit_count = np.zeros(5, int), np.zeros(5, int)
    pending = [None] * 5
    cash_reference, previous_cash = 1000.0, 1000.0
    previous_event = instant(freeze["start_open_utc"])
    public = []

    def accrue(stamp):
        nonlocal previous_event, cash_reference
        require(stamp >= previous_event, "event clock moved backwards")
        growth = 1 + 0.03 * (stamp - previous_event).total_seconds() / (365 * 86400)
        cash_reference *= growth
        for acc in accounts:
            acc["cash"] *= growth
            acc["dividend_cash"] *= growth
            acc["qqq_cash"] *= growth
            acc["qqq_dividend_cash"] *= growth
        previous_event = stamp

    for day_index, row in enumerate(sessions):
        day = row["session"]
        opens, close_at = cal[day]
        actions = [_action(row["symbols"][s]) for s in SYMBOLS]
        bars_by_symbol = [row["symbols"][s]["bars"] for s in SYMBOLS]
        accrue(opens)
        for acc in accounts:
            acc["shares"] *= np.array([a[1] for a in actions])
            dist = acc["shares"] * np.array([a[2] for a in actions])
            acc["cash"] += dist
            acc["dividend_cash"] += dist
            acc["qqq_shares"] *= actions[2][1]
            dist_qqq = acc["qqq_shares"] * actions[2][2]
            acc["qqq_cash"] += dist_qqq
            acc["qqq_dividend_cash"] += dist_qqq
        for bi in range(len(bars_by_symbol[0])):
            stamp = instant(bars_by_symbol[0][bi]["start"])
            accrue(stamp)
            prices = np.array([bars[bi]["open"] for bars in bars_by_symbol], float)
            old_long = logical.copy()
            for acc in accounts:
                slip, fee = acc["slippage_bps"] / 10000, 0.0001
                for i, symbol in enumerate(SYMBOLS):
                    if old_long[i] and acc["dividend_cash"][i] > 0:
                        amount = min(acc["cash"][i], acc["dividend_cash"][i])
                        acc["shares"][i] += amount / prices[i]
                        acc["cash"][i] -= amount
                        acc["dividend_cash"][i] = 0
                    if pending[i] is not None:
                        side, decision, decision_bar_start = pending[i]
                        require(
                            instant(decision) <= stamp
                            and instant(decision_bar_start) < stamp,
                            "confirmed order must execute at a later native bar open",
                        )
                        if side == 1:
                            require(
                                not old_long[i] and acc["shares"][i] == 0,
                                "entry while already long",
                            )
                            fill = prices[i] * (1 + slip)
                            qty = acc["cash"][i] / (fill * (1 + fee))
                            (
                                acc["shares"][i],
                                acc["cash"][i],
                                acc["dividend_cash"][i],
                            ) = qty, 0, 0
                        else:
                            require(old_long[i], "exit while logically flat")
                            fill = prices[i] * (1 - slip)
                            qty = acc["shares"][i]
                            acc["cash"][i] += qty * fill * (1 - fee)
                            acc["shares"][i], acc["dividend_cash"][i] = 0, 0
                        acc["ledger"].append(
                            {
                                "timestamp": stamp.isoformat(),
                                "symbol": symbol,
                                "side": side,
                                "decision_at": decision,
                                "decision_bar_start": decision_bar_start,
                                "quantity": float(qty),
                                "raw_price": float(prices[i]),
                                "fill_price": float(fill),
                                "commission": float(qty * fill * fee),
                                "reason": "normal_strategy",
                            }
                        )
                if acc["qqq_dividend_cash"] > 0:
                    amount = min(acc["qqq_cash"], acc["qqq_dividend_cash"])
                    acc["qqq_shares"] += amount / prices[2]
                    acc["qqq_cash"] -= amount
                    acc["qqq_dividend_cash"] = 0
                if day_index == 0 and bi == 0:
                    acc["qqq_shares"] = acc["qqq_cash"] / (
                        prices[2] * (1 + slip) * (1 + fee)
                    )
                    acc["qqq_cash"] = 0
            for i in range(5):
                if pending[i] is not None:
                    logical[i] = pending[i][0] == 1
                    entry_count[i] = exit_count[i] = 0
                    pending[i] = None
            end = instant(bars_by_symbol[0][bi]["end"])
            accrue(end)  # Same close / next-open clock accrues exactly once.
            for i, symbol in enumerate(SYMBOLS):
                entry, exit_ = features[symbol].preview(
                    float(bars_by_symbol[i][bi]["close"]), actions[i][1], actions[i][2]
                )
                entry_count[i] = entry_count[i] + 1 if not logical[i] and entry else 0
                exit_count[i] = exit_count[i] + 1 if logical[i] and exit_ else 0
                if (not logical[i] and entry_count[i] >= 7) or (
                    logical[i] and exit_count[i] >= 7
                ):
                    pending[i] = (
                        1 if not logical[i] else -1,
                        end.isoformat(),
                        stamp.isoformat(),
                    )
        mark = instant(row["available_at_utc"])
        accrue(mark)
        daily_prices = np.array([a[0] for a in actions])
        for acc in accounts:
            equity = float(fsum(acc["cash"] + acc["shares"] * daily_prices))
            qqq = float(acc["qqq_cash"] + acc["qqq_shares"] * daily_prices[2])
            public.append(
                {
                    "session": day,
                    "timestamp": mark.isoformat(),
                    "slippage_bps": acc["slippage_bps"],
                    "portfolio_return": equity / acc["previous_equity"] - 1,
                    "cash_return": cash_reference / previous_cash - 1,
                    "qqq_bh_return": qqq / acc["previous_qqq"] - 1,
                }
            )
            acc["previous_equity"], acc["previous_qqq"] = equity, qqq
        previous_cash = cash_reference
        for i, symbol in enumerate(SYMBOLS):
            features[symbol].finalize(*actions[i])
    private = {
        "cash_reference": cash_reference,
        "last_event_utc": previous_event.isoformat(),
        "logical_long": logical.tolist(),
        "entry_streaks": entry_count.tolist(),
        "exit_streaks": exit_count.tolist(),
        "pending": pending,
        "accounts": accounts,
    }

    def serial(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, dict):
            return {k: serial(v) for k, v in value.items()}
        if isinstance(value, list):
            return [serial(v) for v in value]
        return value

    return public, serial(private)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=PUBLIC_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()
