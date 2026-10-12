#!/usr/bin/env python3

import argparse
import re
from datetime import datetime, timedelta, time
import config

LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"indoor (?P<indoor>\S+) "
    r"dhw (?P<dhw>\S+) "
    r"dhw_temp (?P<dhw_temp>\S+) "
    r"output (?P<output>\S+) "
    r"electricity_price (?P<price>\S+) "
    r"set_temp (?P<set_temp>\S+)"
)


def read_log(filename):
    entries = []

    with open(filename, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()

            if not line:
                continue

            match = LINE_RE.match(line)

            if not match:
                print(
                    f"Warning: could not parse line "
                    f"{line_number}: {line}"
                )
                continue

            data = match.groupdict()

            entries.append(
                {
                    "timestamp": datetime.strptime(
                        data["timestamp"],
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    "output": float(data["output"]),
                    "price": float(data["price"]),
                }
            )

    entries.sort(key=lambda entry: entry["timestamp"])
    return entries


def parse_update_time(value):
    """Parse an HH:MM daily update time."""
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Update time must be in HH:MM format"
        ) from exc


def get_period_start(timestamp, update_time):
    """Return the start of the 24-hour period containing timestamp."""
    start = datetime.combine(timestamp.date(), update_time)

    if timestamp < start:
        start -= timedelta(days=1)

    return start


def calculate_costs(entries, update_time):
    if len(entries) < 2:
        raise RuntimeError(
            "At least two valid log entries are required."
        )

    # Accumulate observed energy and costs by 24-hour heating period.
    periods = {}

    for current, next_entry in zip(entries, entries[1:]):
        start = current["timestamp"]
        end = next_entry["timestamp"]
        dt_hours = (end - start).total_seconds() / 3600.0

        if dt_hours <= 0:
            continue

        # Avoid treating long logging gaps as continuous operation.
        # Gaps above this limit are ignored rather than extrapolated.
        if dt_hours > 5 / 60:
            print(
                f"Warning: ignoring logging gap of {dt_hours:.2f} h "
                f"starting at {start}"
            )
            continue

        # Split an interval if it crosses a daily period boundary.
        segment_start = start

        while segment_start < end:
            period_start = get_period_start(
                segment_start, update_time
            )
            period_end = period_start + timedelta(days=1)
            segment_end = min(end, period_end)

            segment_hours = (
                segment_end - segment_start
            ).total_seconds() / 3600.0

            period = periods.setdefault(
                period_start,
                {
                    "hours": 0.0,
                    "energy_kwh": 0.0,
                    "actual_cost": 0.0,
                    "price_hours": 0.0,
                    "price_time_cost": 0.0,
                },
            )

            energy_kwh = current["output"] * segment_hours

            period["hours"] += segment_hours
            period["energy_kwh"] += energy_kwh
            period["actual_cost"] += (
                energy_kwh * current["price"]
            )
            period["price_hours"] += segment_hours
            period["price_time_cost"] += (
                current["price"] * segment_hours
            )

            segment_start = segment_end

    total_hours = 0.0
    total_energy = 0.0
    actual_cost = 0.0
    uniform_cost = 0.0
    included_periods = 0

    for period_start, period in sorted(periods.items()):
        hours = period["hours"]

        if hours <= 0:
            continue

        energy = period["energy_kwh"]

        # Normalize observed energy to a full 24-hour day.
        # This assumes the observed average power represents
        # the heating energy needed for the entire period.
        daily_energy = energy * 24.0 / hours
        average_power = daily_energy / 24.0

        # Actual cost is also normalized to a full day, so the
        # comparison uses the same estimated daily energy on both sides.
        daily_actual_cost = (
            period["actual_cost"] * 24.0 / hours
        )

        # For a uniform load, each hour has the same average power.
        # Use the time-weighted average price from the observed data.
        average_price = (
            period["price_time_cost"] / period["price_hours"]
        )
        daily_uniform_cost = daily_energy * average_price

        total_hours += 24.0
        total_energy += daily_energy
        actual_cost += daily_actual_cost
        uniform_cost += daily_uniform_cost
        included_periods += 1

    if included_periods == 0:
        raise RuntimeError(
            "No valid daily periods found in the log."
        )

    saving = uniform_cost - actual_cost
    saving_percent = (
        100.0 * saving / uniform_cost
        if uniform_cost != 0
        else 0.0
    )

    return {
        "start": entries[0]["timestamp"],
        "end": entries[-1]["timestamp"],
        "periods": included_periods,
        "duration_hours": total_hours,
        "energy_kwh": total_energy,
        "average_power_kw": total_energy / total_hours,
        "actual_cost": actual_cost,
        "uniform_cost": uniform_cost,
        "saving": saving,
        "saving_percent": saving_percent,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare logged electricity cost with a uniform load "
            "within each daily heating period."
        )
    )

    parser.add_argument("filename", help="Log file to analyze")
    parser.add_argument(
        "--update-time",
        type=parse_update_time,
        default=parse_update_time(
            config.HEATING_PERIODS_UPDATE_TIME_OF_DAY
        ),
        help=(
            "Start time of each 24-hour heating period "
            "(HH:MM). Defaults to config.py."
        ),
    )

    args = parser.parse_args()

    entries = read_log(args.filename)

    if not entries:
        raise RuntimeError("Log contains no valid entries.")

    result = calculate_costs(entries, args.update_time)

    print()
    print("Ecodan electricity cost analysis")
    print("--------------------------------")
    print(f"Start:              {result['start']}")
    print(f"End:                {result['end']}")
    print(f"Heating periods:    {result['periods']}")
    print(f"Equivalent days:    {result['duration_hours'] / 24:.2f}")
    print()
    print(f"Total energy:       {result['energy_kwh']:.3f} kWh")
    print(f"Average power:      {result['average_power_kw']:.3f} kW")
    print()
    print(f"Actual cost:        {result['actual_cost'] / 100:.3f} €")
    print(f"Uniform cost:       {result['uniform_cost'] / 100:.3f} €")
    print(f"Saving:             {result['saving'] / 100:.3f} €")
    print(f"Saving percentage:  {result['saving_percent']:.2f} %")
    print()


if __name__ == "__main__":
    main()
