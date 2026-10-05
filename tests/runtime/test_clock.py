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


def test_the_reference_morning_is_a_monday_at_eight_utc() -> None:
    assert REFERENCE_MORNING == utc(2026, 6, 29, 8)
    assert REFERENCE_MORNING.weekday() == 0


def test_sim_now_is_the_reference_morning_at_run_start() -> None:
    start = utc(2026, 10, 5, 13, 7)
    assert sim_now(REFERENCE_MORNING, start, start) == REFERENCE_MORNING


def test_sim_now_advances_with_real_time_one_to_one() -> None:
    start = utc(2026, 10, 5, 13, 7)
    assert sim_now(REFERENCE_MORNING, start, start + timedelta(hours=5, seconds=3)) == utc(
        2026, 6, 29, 13
    ) + timedelta(seconds=3)


def test_sim_now_crosses_a_weekend_in_real_elapsed_time() -> None:
    start = utc(2026, 10, 5, 13, 7)
    assert sim_now(REFERENCE_MORNING, start, start + timedelta(days=5)) == utc(2026, 7, 4, 8)


def test_sim_now_converts_other_offsets_to_utc() -> None:
    start = datetime.fromisoformat("2026-10-05T15:07:00+02:00")
    assert sim_now(REFERENCE_MORNING, start, start + timedelta(hours=1)) == utc(2026, 6, 29, 9)


def test_a_naive_timestamp_is_refused() -> None:
    naive = datetime(2026, 6, 29, 8)
    with pytest.raises(ValueError, match="time zone"):
        sim_now(REFERENCE_MORNING, naive, naive)
    with pytest.raises(ValueError, match="time zone"):
        age_business_days(naive, REFERENCE_MORNING)


timestamps = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
)


def test_age_within_one_weekday_is_the_fraction_of_a_day() -> None:
    assert age_business_days(utc(2026, 6, 29, 8), utc(2026, 6, 29, 20)) == pytest.approx(0.5)


def test_age_from_friday_noon_to_monday_noon_is_one_business_day() -> None:
    assert age_business_days(utc(2026, 7, 3, 12), utc(2026, 7, 6, 12)) == pytest.approx(1.0)


def test_the_weekend_adds_no_age() -> None:
    assert age_business_days(utc(2026, 7, 3, 12), utc(2026, 7, 5, 23)) == pytest.approx(0.5)
    assert age_business_days(utc(2026, 7, 4, 9), utc(2026, 7, 5, 9)) == 0.0


def test_a_lead_received_on_a_saturday_ages_from_monday_midnight() -> None:
    assert age_business_days(utc(2026, 7, 4, 10), utc(2026, 7, 6, 12)) == pytest.approx(0.5)


def test_a_business_day_is_a_utc_day_whatever_the_offset_given() -> None:
    # Friday 22:00 at -05:00 is Saturday 03:00 UTC, a weekend moment, so the lead ages from Monday 00:00 UTC.
    received = datetime.fromisoformat("2026-07-03T22:00:00-05:00")
    assert age_business_days(received, utc(2026, 7, 6)) == 0.0
    # Monday 01:00 at +02:00 is Sunday 23:00 UTC, which adds nothing.
    now = datetime.fromisoformat("2026-07-06T01:00:00+02:00")
    assert age_business_days(utc(2026, 7, 3, 12), now) == pytest.approx(0.5)


def test_age_across_a_full_week_is_five_business_days() -> None:
    assert age_business_days(REFERENCE_MORNING, utc(2026, 7, 6, 8)) == pytest.approx(5.0)


def test_age_is_negative_for_a_lead_received_after_now() -> None:
    assert age_business_days(utc(2026, 6, 29, 20), utc(2026, 6, 29, 8)) == pytest.approx(-0.5)


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


@given(start=timestamps, hours=st.integers(min_value=0, max_value=24 * 30))
def test_age_never_exceeds_elapsed_calendar_days(start: datetime, hours: int) -> None:
    elapsed = timedelta(hours=hours)
    age = age_business_days(start, start + elapsed)
    assert 0 <= age <= elapsed / timedelta(days=1) + 1e-9
