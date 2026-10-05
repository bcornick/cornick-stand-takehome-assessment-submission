# ABOUTME: Tests the simulated clock of 7.6: sim_now from the reference morning, run start and real now, and UTC business days Monday to Friday.
# ABOUTME: Examples pin a Friday afternoon, a weekend and a full week; Hypothesis properties check the age against a day-by-day count of weekday fractions.
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from uwh.runtime.clock import age_business_days, sim_now
from uwh.skills.vertical import REFERENCE_MORNING

SATURDAY = 5


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_sim_now_starts_at_the_reference_morning_and_advances_with_real_time_one_to_one() -> None:
    start = utc(2026, 10, 5, 13, 7)
    assert sim_now(REFERENCE_MORNING, start, start) == REFERENCE_MORNING
    assert sim_now(REFERENCE_MORNING, start, start + timedelta(hours=5, seconds=3)) == utc(
        2026, 6, 29, 13
    ) + timedelta(seconds=3)
    assert sim_now(REFERENCE_MORNING, start, start + timedelta(days=5)) == utc(2026, 7, 4, 8)


@pytest.mark.parametrize(
    ("received", "now", "days"),
    [
        (utc(2026, 6, 29, 8), utc(2026, 6, 29, 20), 0.5),  # within one weekday
        (utc(2026, 7, 3, 12), utc(2026, 7, 6, 12), 1.0),  # Friday noon to Monday noon
        (utc(2026, 7, 3, 12), utc(2026, 7, 5, 23), 0.5),  # the weekend adds nothing
        (utc(2026, 7, 4, 10), utc(2026, 7, 6, 12), 0.5),  # received on a Saturday: ages from Monday
        # Friday 22:00 at -05:00 is Saturday 03:00 UTC, so the lead ages from Monday 00:00 UTC.
        (datetime.fromisoformat("2026-07-03T22:00:00-05:00"), utc(2026, 7, 6), 0.0),
        # Monday 01:00 at +02:00 is Sunday 23:00 UTC, which adds nothing.
        (utc(2026, 7, 3, 12), datetime.fromisoformat("2026-07-06T01:00:00+02:00"), 0.5),
    ],
)
def test_age_counts_business_days_in_utc(received: datetime, now: datetime, days: float) -> None:
    assert age_business_days(received, now) == pytest.approx(days)


timestamps = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
)


def weekday_fractions_between(start: datetime, end: datetime) -> float:
    """Each UTC weekday contributes the fraction of its 24 hours that lies between start and end; Saturday and Sunday contribute nothing."""
    total = 0.0
    day_start = datetime.combine(start.date(), datetime.min.time(), tzinfo=UTC)
    while day_start <= end:
        if day_start.weekday() < SATURDAY:
            overlap = min(end, day_start + timedelta(days=1)) - max(start, day_start)
            total += max(overlap, timedelta(0)) / timedelta(days=1)
        day_start += timedelta(days=1)
    return total


@given(
    start=timestamps, length=st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=400))
)
def test_age_is_the_weekday_fractions_of_the_span(start: datetime, length: timedelta) -> None:
    end = start + length
    assert age_business_days(start, end) == pytest.approx(
        weekday_fractions_between(start, end), abs=1e-9
    )
