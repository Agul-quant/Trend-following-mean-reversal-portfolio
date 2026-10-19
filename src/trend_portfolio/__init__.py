"""Retrospective, static-initial-capital portfolio analytics. Not trading software."""

from .analytics import (
    cap_diagnostics,
    joint_regression,
    max_cagr_weights,
    metrics,
    optimize_sharpe,
    pairwise_regressions,
    portfolio_equity,
    returns_from_equity,
)

__all__ = [
    "cap_diagnostics", "joint_regression", "max_cagr_weights", "metrics",
    "optimize_sharpe", "pairwise_regressions", "portfolio_equity",
    "returns_from_equity",
]
