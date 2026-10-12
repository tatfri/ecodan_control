#!/usr/bin/env python3

import argparse
import re
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


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
    timestamps = []
    indoor = []
    dhw = []
    dhw_temp = []
    output = []
    price = []
    set_temp = []

    with open(filename, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()

            if not line:
                continue

            match = LINE_RE.match(line)

            if not match:
                print(f"Warning: could not parse line {line_number}: {line}")
                continue

            data = match.groupdict()

            timestamps.append(
                datetime.strptime(
                    data["timestamp"],
                    "%Y-%m-%d %H:%M:%S",
                )
            )

            indoor.append(int(data["indoor"]))
            dhw.append(int(data["dhw"]))
            dhw_temp.append(float(data["dhw_temp"]))
            output.append(float(data["output"]))
            price.append(float(data["price"]))
            set_temp.append(float(data["set_temp"]))

    return {
        "timestamps": timestamps,
        "indoor": indoor,
        "dhw": dhw,
        "dhw_temp": dhw_temp,
        "output": output,
        "price": price,
        "set_temp": set_temp,
    }


def add_background_regions(ax, timestamps, indoor, dhw):
    """
    Add background shading for heating and DHW operation.

    Green  = indoor != 0
    Yellow = dhw != 0
    """

    if not timestamps:
        return

    # Extend the first/last interval slightly so that the
    # background also covers the complete visible area.
    if len(timestamps) > 1:
        half_interval = (timestamps[1] - timestamps[0]) / 2
    else:
        half_interval = (timestamps[0] - timestamps[0])

    start = timestamps[0] - half_interval
    end = timestamps[-1] + half_interval

    # Build contiguous regions.
    regions = []

    current_start = start
    current_state = (indoor[0] != 0, dhw[0] != 0)

    for i in range(1, len(timestamps)):
        state = (indoor[i] != 0, dhw[i] != 0)

        if state != current_state:
            regions.append(
                (current_start, timestamps[i], current_state)
            )

            current_start = timestamps[i]
            current_state = state

    regions.append((current_start, end, current_state))

    for region_start, region_end, state in regions:
        heating, hot_water = state

#        if heating and hot_water:
#            # Both active: use a neutral light color.
#            ax.axvspan(
#                region_start,
#                region_end,
#                color="green",
#                alpha=0.35,
#                zorder=0,
#            )
#            ax.axvspan(
#                region_start,
#                region_end,
#                color="yellow",
#                alpha=0.35,
#                zorder=0,
#            )
#
#        elif heating:
#            ax.axvspan(
#                region_start,
#                region_end,
#                color="green",
#                alpha=0.35,
#                zorder=0,
#            )
#
#        elif hot_water:
#            ax.axvspan(
#                region_start,
#                region_end,
#                color="yellow",
#                alpha=0.35,
#                zorder=0,
#            )


def plot_log(data):
    timestamps = data["timestamps"]

    if not timestamps:
        raise RuntimeError("Log contains no valid entries.")

    fig, ax_price = plt.subplots(figsize=(14, 7))

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------

    add_background_regions(
        ax_price,
        timestamps,
        data["indoor"],
        data["dhw"],
    )

    # ------------------------------------------------------------------
    # Electricity price
    # ------------------------------------------------------------------

    price_line = ax_price.plot(
        timestamps,
        data["price"],
        label="Electricity price",
        linewidth=1.5,
        color="red"
    )

    ax_price.set_ylabel("Electricity price (c/kWh)")
    ax_price.set_xlabel("Time")

    # ------------------------------------------------------------------
    # Heating output
    # ------------------------------------------------------------------

    ax_output = ax_price.twinx()

    output_line = ax_output.plot(
        timestamps,
        data["output"],
        label="Output",
        linewidth=1.5,
    )

    ax_output.set_ylabel("Output (kW)")

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    ax_price.xaxis.set_major_locator(
        mdates.AutoDateLocator()
    )

    ax_price.xaxis.set_major_formatter(
        mdates.DateFormatter("%d.%m. %H:%M")
    )

    fig.autofmt_xdate()

    # Combine legends from both y-axes.
    lines = price_line + output_line
    labels = [line.get_label() for line in lines]

    ax_price.legend(
        lines,
        labels,
        loc="upper left",
    )

    ax_price.grid(
        True,
        axis="y",
        alpha=0.3,
    )

    ax_price.set_title("Ecodan log")

    fig.tight_layout()

    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Plot Ecodan controller log."
    )

    parser.add_argument(
        "filename",
        help="Log file to plot",
    )

    args = parser.parse_args()

    data = read_log(args.filename)
    plot_log(data)


if __name__ == "__main__":
    main()

