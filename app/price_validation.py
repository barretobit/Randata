"""Checks that decide whether a daily price bar is trustworthy.

Two rules, used both when fetching new bars and when auditing stored ones:

1. Structure: open, high, low and close are positive, finite and consistent.
2. Spikes: a close that jumps away and comes straight back (an isolated
   provider glitch) is rejected. Real moves such as earnings gaps, crashes or
   rallies stay at their new level on the following days and are kept.
"""

import math
import statistics

import pandas as pd

from .config import (
    PRICE_HARD_MAX_RETURN,
    PRICE_OUTLIER_MIN_RETURN,
    PRICE_OUTLIER_MIN_SAMPLES,
    PRICE_OUTLIER_SIGMA,
)

# How many recent close-to-close moves are used to judge whether a new move is abnormal.
RECENT_MOVES_WINDOW = 60
# Moves across a weekend plus a holiday still count as one daily move.
MAX_DAILY_MOVE_GAP_DAYS = 4
# Relative slack allowed when checking that open and close lie between low and high.
_OHLC_TOLERANCE = 0.005
# Median absolute deviation x 1.4826 estimates the standard deviation of normal data.
_DEVIATION_TO_STANDARD_DEVIATION = 1.4826


def finite_number(value) -> float | None:
    """The value as a finite float, or None for missing, NaN, infinite or non-numeric values."""
    if value is None or pd.isna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def valid_ohlc(values) -> bool:
    """Whether (open, high, low, close) are positive, finite and consistent with each other."""
    try:
        open_price, high, low, close = (float(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        all(math.isfinite(value) and value > 0 for value in (open_price, high, low, close))
        and low <= high
        and low * (1 - _OHLC_TOLERANCE) <= open_price <= high * (1 + _OHLC_TOLERANCE)
        and low * (1 - _OHLC_TOLERANCE) <= close <= high * (1 + _OHLC_TOLERANCE)
    )


def is_abnormal_move(move: float, recent_moves: list[float], elapsed_days: int = 1) -> bool:
    """Whether a close-to-close move is far outside the asset's recent behaviour.

    Above PRICE_HARD_MAX_RETURN a move is always abnormal. Otherwise, once there
    are enough recent moves, it is compared with a robust z-score: the median
    absolute deviation of recent moves, scaled to a standard deviation. The
    limit widens with the square root of the days elapsed and never drops
    below PRICE_OUTLIER_MIN_RETURN.
    """
    if abs(move) > PRICE_HARD_MAX_RETURN:
        return True
    if len(recent_moves) < PRICE_OUTLIER_MIN_SAMPLES:
        return False
    typical_move = statistics.median(recent_moves)
    deviation = statistics.median(abs(value - typical_move) for value in recent_moves)
    gap_scale = math.sqrt(max(1, elapsed_days - 2))
    limit = max(
        PRICE_OUTLIER_SIGMA * _DEVIATION_TO_STANDARD_DEVIATION * deviation * gap_scale,
        PRICE_OUTLIER_MIN_RETURN * gap_scale,
    )
    return abs(move - typical_move) > limit


def find_price_spikes(closes: list[tuple]) -> set[int]:
    """Indexes of isolated spikes in a chronological list of (date, close) pairs.

    A spike jumps abnormally away from the previous kept close, then the next
    close comes back at least halfway with another abnormal move. A real move
    stays at its new level, so it is kept. The last bar has no next bar to
    confirm a reversal, so it is only rejected above the hard move limit; the
    nightly overlap window re-checks it once the next bar exists.
    """
    spikes = set()
    if not closes:
        return spikes
    recent_moves = []
    previous_date, previous_close = closes[0]
    for index in range(1, len(closes)):
        bar_date, close = closes[index]
        move_in = close / previous_close - 1
        elapsed_days = (bar_date - previous_date).days
        if index + 1 < len(closes):
            next_date, next_close = closes[index + 1]
            comes_back = abs(next_close / previous_close - 1) < abs(move_in) / 2
            is_spike = (
                comes_back
                and is_abnormal_move(move_in, recent_moves, elapsed_days)
                and is_abnormal_move(next_close / close - 1, recent_moves, (next_date - bar_date).days)
            )
        else:
            is_spike = abs(move_in) > PRICE_HARD_MAX_RETURN
        if is_spike:
            spikes.add(index)
            continue
        if elapsed_days <= MAX_DAILY_MOVE_GAP_DAYS:
            recent_moves.append(move_in)
            recent_moves = recent_moves[-RECENT_MOVES_WINDOW:]
        previous_date, previous_close = bar_date, close
    return spikes


def frame_to_bars(symbol: str, frame: pd.DataFrame) -> tuple[list[dict], list]:
    """Split a Yahoo frame into upsert-ready bar dicts and the dates of structurally invalid rows."""
    bars = []
    invalid_dates = []
    for timestamp, row in frame.sort_index().iterrows():
        open_price, high, low, close = (
            finite_number(row[column]) for column in ("Open", "High", "Low", "Close")
        )
        if not valid_ohlc((open_price, high, low, close)):
            invalid_dates.append(timestamp.date())
            continue
        volume = finite_number(row["Volume"])
        bars.append({
            "symbol": symbol,
            "date":   timestamp.date(),
            "open":   open_price,
            "high":   high,
            "low":    low,
            "close":  close,
            "volume": int(volume) if volume is not None else None,
        })
    return bars, invalid_dates


def find_suspicious_bars(bars: list[dict]) -> list:
    """Dates of stored bars that are structurally invalid or isolated price spikes."""
    suspicious = []
    closes = []
    for bar in bars:
        if valid_ohlc((bar["open"], bar["high"], bar["low"], bar["close"])):
            closes.append((bar["date"], bar["close"]))
        else:
            suspicious.append(bar["date"])
    suspicious.extend(closes[index][0] for index in find_price_spikes(closes))
    return sorted(suspicious)
