# ABOUTME: The simulated clock of 7.6: sim_now from the reference morning, the run start and the real now, and business days counted in UTC, Monday to Friday.
# ABOUTME: Pure functions of the values passed in; nothing here reads the system clock, so a test passes the real clock in.
from datetime import UTC, datetime, timedelta

WEEKDAYS_PER_WEEK = 5
ONE_DAY = timedelta(days=1)


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("a timestamp needs a time zone")
    return moment.astimezone(UTC)


def sim_now(reference_morning: datetime, run_start: datetime, real_now: datetime) -> datetime:
    """`reference_morning + (real_now - run_start)`, in UTC."""
    return _utc(reference_morning) + (_utc(real_now) - _utc(run_start))


def _business_days_elapsed(moment: datetime) -> float:
    """Business days from a fixed Monday to `moment`; a weekend day adds nothing and a weekday adds its elapsed fraction."""
    moment = _utc(moment)
    weeks, day_of_week = divmod(moment.toordinal() - 1, 7)  # ordinal 1 is a Monday
    whole_days = weeks * WEEKDAYS_PER_WEEK + min(day_of_week, WEEKDAYS_PER_WEEK)
    if day_of_week >= WEEKDAYS_PER_WEEK:
        return float(whole_days)
    time_of_day = moment - moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return whole_days + time_of_day / ONE_DAY


def age_business_days(received_at: datetime, now: datetime) -> float:
    """Business days from `received_at` to `now`, a Monday-to-Friday UTC day counting as 1 and Saturday and Sunday as 0.

    Friday 12:00 to Monday 12:00 is 1.0. A lead received on a weekend ages from Monday 00:00. The result is
    negative when `received_at` is after `now`.
    """
    return _business_days_elapsed(now) - _business_days_elapsed(received_at)
