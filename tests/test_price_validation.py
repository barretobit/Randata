from datetime import date, timedelta

from app import ingestion, yahoo
from app.price_validation import find_suspicious_bars
from conftest import frame_dates, make_frame, price_row, random_walk


def stored_dates(session):
    return [bar["date"] for bar in session.writes]


def test_real_earnings_drop_is_kept(fake_session):
    closes = random_walk(150, 0.015)
    closes[90:] *= 0.74  # -26% gap that stays
    frame = make_frame(closes)

    written = ingestion._store_frame("TEST", frame)

    assert written == 150
    assert stored_dates(fake_session) == frame_dates(frame)


def test_real_rally_on_calm_etf_is_kept(fake_session):
    closes = random_walk(150, 0.008)
    closes[90:] *= 1.15
    assert ingestion._store_frame("TEST", make_frame(closes)) == 150


def test_isolated_spike_is_skipped(fake_session):
    closes = random_walk(150, 0.015)
    closes[90] *= 1.5  # one bad bar, next day back to normal
    frame = make_frame(closes)

    written = ingestion._store_frame("TEST", frame)

    assert written == 149
    assert frame_dates(frame)[90] not in stored_dates(fake_session)
    # Stored the night before (when it was still the newest bar): removed now that it is confirmed.
    assert fake_session.deletes == [{"symbol": "TEST", "dates": [frame_dates(frame)[90]]}]


def test_real_moves_delete_nothing(fake_session):
    closes = random_walk(150, 0.015)
    closes[90:] *= 0.74
    ingestion._store_frame("TEST", make_frame(closes))
    assert fake_session.deletes == []


def test_gap_fill_is_checked_against_the_stored_bar_after_it(fake_session):
    stored_closes = random_walk(61, 0.01)
    start = date(2023, 10, 2)
    prior_rows = [price_row(start + timedelta(days=offset), close) for offset, close in enumerate(stored_closes)]
    level = stored_closes[-1]
    gap_frame = make_frame([level * 1.6], start="2024-01-02")
    next_stored = price_row(date(2024, 1, 3), level * 1.001)
    fake_session.reads = [list(reversed(prior_rows)), [next_stored]]

    # Without the bar after the gap, a 60% jump on the last bar would be stored.
    assert ingestion._store_frame("TEST", gap_frame) == 0
    assert fake_session.deletes == [{"symbol": "TEST", "dates": [date(2024, 1, 2)]}]


def test_hundredfold_glitch_is_skipped_even_without_history(fake_session):
    closes = random_walk(10, 0.01)
    closes[5] *= 100
    frame = make_frame(closes)

    assert ingestion._store_frame("TEST", frame) == 9
    assert frame_dates(frame)[5] not in stored_dates(fake_session)


def test_last_bar_waits_only_above_hard_limit(fake_session):
    big_move = random_walk(100, 0.01)
    big_move[-1] *= 1.3  # abnormal but plausible: stored now
    assert ingestion._store_frame("TEST", make_frame(big_move)) == 100

    fake_session.writes.clear()
    impossible_move = random_walk(100, 0.01)
    impossible_move[-1] *= 3  # above the 80% hard limit: wait for the next bar
    assert ingestion._store_frame("TEST", make_frame(impossible_move)) == 99


def test_spike_check_uses_stored_bars_before_the_frame(fake_session):
    stored_closes = random_walk(61, 0.01)
    start = date(2023, 10, 2)
    stored_rows = [price_row(start + timedelta(days=offset), close) for offset, close in enumerate(stored_closes)]
    fake_session.reads = [list(reversed(stored_rows))]  # the query reads newest first
    level = stored_closes[-1]
    frame = make_frame([level * 1.6, level, level * 1.001], start="2024-01-02")

    assert ingestion._store_frame("TEST", frame) == 2
    assert frame_dates(frame)[0] not in stored_dates(fake_session)


def test_upserts_are_sent_as_one_batch(fake_session):
    ingestion._store_frame("TEST", make_frame(random_walk(30, 0.01)))
    assert fake_session.commits == 1
    assert len(fake_session.writes) == 30


def test_invalid_ohlc_bar_is_skipped(fake_session):
    frame = make_frame(random_walk(10, 0.01))
    frame.iloc[4, frame.columns.get_loc("High")] = 1.0  # high below low
    assert ingestion._store_frame("TEST", frame) == 9


def test_readjusted_history_is_detected(fake_session):
    frame = make_frame([100, 101, 102, 103, 104])
    days = frame_dates(frame)
    fake_session.reads = [[price_row(day, close / 0.98) for day, close in zip(days, [100, 101, 102, 103])]]
    assert ingestion._history_was_readjusted("TEST", frame)


def test_matching_history_is_not_readjusted(fake_session):
    frame = make_frame([100, 101, 102, 103, 104])
    days = frame_dates(frame)
    # Only the newest stored day differs: it was a still-open trading day.
    stored = [price_row(day, close) for day, close in zip(days, [100, 101, 102, 90])]
    fake_session.reads = [stored]
    assert not ingestion._history_was_readjusted("TEST", frame)


def test_ingest_daily_refetches_full_window_after_split(fake_session, monkeypatch):
    frame = make_frame([50, 50.5, 51, 51.5, 52])
    days = frame_dates(frame)
    fake_session.reads = [
        [(days[3],)],  # MAX(date)
        [price_row(day, close * 2) for day, close in zip(days, [50, 50.5, 51, 51.5])],
    ]
    monkeypatch.setattr(yahoo, "download", lambda *arguments, **keywords: frame)
    backfilled = []
    monkeypatch.setattr(ingestion, "backfill", lambda symbol, **keywords: backfilled.append(symbol) or 2500)

    assert ingestion.ingest_daily("TEST") == 2500
    assert backfilled == ["TEST"]
    assert fake_session.writes == []


def test_audit_flags_spikes_and_invalid_bars_but_not_crashes():
    closes = random_walk(120, 0.012)
    closes[60:] *= 0.88  # crash that stays: not suspicious
    closes[100] *= 1.4  # isolated spike: suspicious
    start = date(2024, 1, 1)
    bars = [
        {"date": start + timedelta(days=offset), "open": close, "high": close * 1.005,
         "low": close * 0.995, "close": close, "volume": 1}
        for offset, close in enumerate(closes)
    ]
    bars[30]["high"] = None

    assert find_suspicious_bars(bars) == [bars[30]["date"], bars[100]["date"]]


def test_only_one_bulk_job_runs_at_a_time():
    with ingestion._exclusive_bulk_job("first job"):
        try:
            with ingestion._exclusive_bulk_job("second job"):
                raise AssertionError("second job must not start")
        except ingestion.IngestionAlreadyRunning:
            pass
    with ingestion._exclusive_bulk_job("third job"):
        pass
