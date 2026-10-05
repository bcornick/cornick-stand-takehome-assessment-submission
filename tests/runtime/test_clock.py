# ABOUTME: Tests the simulated clock of 7.6: sim_now from the reference morning, run start and real now, and UTC business days Monday to Friday.
# ABOUTME: A Hypothesis property checks that adding N business days never lands on a weekend and spans exactly N weekdays; examples pin a Friday afternoon, a Saturday start and the reference morning.
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from uwh.runtime.clock import add_business_days, age_business_days, sim_now
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
        add_business_days(naive, 1)
    with pytest.raises(ValueError, match="time zone"):
        age_business_days(naive, REFERENCE_MORNING)


def test_one_business_day_from_a_friday_afternoon_is_monday_at_the_same_time() -> None:
    assert add_business_days(utc(2026, 7, 3, 16, 45), 1) == utc(2026, 7, 6, 16, 45)


def test_two_business_days_from_the_reference_morning_is_wednesday() -> None:
    assert add_business_days(REFERENCE_MORNING, 2) == utc(2026, 7, 1, 8)


def test_business_days_from_a_saturday_start_at_the_next_monday() -> None:
    saturday = utc(2026, 7, 4, 10)
    assert add_business_days(saturday, 1) == utc(2026, 7, 6, 10)
    assert add_business_days(saturday, 2) == utc(2026, 7, 7, 10)
    assert add_business_days(utc(2026, 7, 5, 23, 59), 1) == utc(2026, 7, 6, 23, 59)


def test_a_week_of_business_days_is_seven_calendar_days() -> None:
    assert add_business_days(REFERENCE_MORNING, 5) == utc(2026, 7, 6, 8)


def test_the_day_is_taken_in_utc_not_in_the_offset_given() -> None:
    # 2026-07-03 22:00 -05:00 is Saturday 2026-07-04 03:00 UTC.
    start = datetime.fromisoformat("2026-07-03T22:00:00-05:00")
    assert add_business_days(start, 1) == utc(2026, 7, 6, 3)


def test_business_days_must_be_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        add_business_days(REFERENCE_MORNING, 0)


def weekdays_after_through(start: datetime, end: datetime) -> int:
    """Weekdays among the UTC dates after start's date, up to and including end's date; counted one calendar day at a time."""
    day = start.date()
    count = 0
    while day < end.date():
        day += timedelta(days=1)
        if day.weekday() < SATURDAY:
            count += 1
    return count


timestamps = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
)


@given(start=timestamps, n=st.integers(min_value=1, max_value=400))
def test_adding_business_days_never_lands_on_a_weekend_and_spans_exactly_n_weekdays(
    start: datetime, n: int
) -> None:
    result = add_business_days(start, n)
    assert result.weekday() < SATURDAY
    assert result.tzinfo == UTC
    assert result.timetz() == start.timetz()
    assert weekdays_after_through(start, result) == n


@given(
    start=timestamps.filter(lambda moment: moment.weekday() < SATURDAY),
    n=st.integers(min_value=1, max_value=400),
)
def test_the_age_of_a_weekday_start_after_n_business_days_is_n(start: datetime, n: int) -> None:
    assert age_business_days(start, add_business_days(start, n)) == pytest.approx(n)


def test_age_within_one_weekday_is_the_fraction_of_a_day() -> None:
    assert age_business_days(utc(2026, 6, 29, 8), utc(2026, 6, 29, 20)) == pytest.approx(0.5)


def test_age_from_friday_noon_to_monday_noon_is_one_business_day() -> None:
    assert age_business_days(utc(2026, 7, 3, 12), utc(2026, 7, 6, 12)) == pytest.approx(1.0)


def test_the_weekend_adds_no_age() -> None:
    assert age_business_days(utc(2026, 7, 3, 12), utc(2026, 7, 5, 23)) == pytest.approx(0.5)
    assert age_business_days(utc(2026, 7, 4, 9), utc(2026, 7, 5, 9)) == 0.0


def test_a_lead_received_on_a_saturday_ages_from_monday_midnight() -> None:
    assert age_business_days(utc(2026, 7, 4, 10), utc(2026, 7, 6, 12)) == pytest.approx(0.5)


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
