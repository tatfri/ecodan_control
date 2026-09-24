import json
import urllib.request
import time
from datetime import datetime
import bisect

# This endpoint returns the latest 48h of electricity prices. Request made after 14:00
# Finnish time will normally include prices for the current day and the next day.
ENDPOINT = "https://api.porssisahko.net/v2/latest-prices.json"

prices = None

def clear():
    global prices
    prices = None

def _parse_timestamp(timestamp: str) -> float:
    return datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    ).timestamp()

def _fetch_prices_json():
    request = urllib.request.Request(
        ENDPOINT,
        headers={
            "User-Agent": "EcodanController/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

def fetch_prices():
    print("Fetching electricity prices...")

    json_data = _fetch_prices_json()

    # Convert to list of start_time, end_time, price tuples
    _prices = []
    for item in json_data["prices"]:
        price = item["price"]
        start_date = item["startDate"]
        end_date = item["endDate"]

        _prices.append((_parse_timestamp(start_date), _parse_timestamp(end_date), price))

    _prices.reverse()
    return _prices

def _maybe_fetch_prices():
    global prices
    if prices is None:
        prices = fetch_prices()

def get_price_at(timestamp: float) -> float:
    _maybe_fetch_prices()

    # Prices are assumed to be sorted by start time so we can search by bisecting
    i = bisect.bisect_right(prices, (timestamp, float('inf'), float('inf')))

    if i:
        start, end, price = prices[i-1]
        if start <= timestamp < end:
            return price

    _, _, price = prices[0]
    return price

def get_average_price(start_time, end_time):
    _maybe_fetch_prices()

    relevant_prices = [p for p in prices if p[1] >= start_time and p[0] <= end_time]
    if not relevant_prices:
        return 0.0

    total_price = 0.0
    total_duration = 0.0
    for start, end, price in relevant_prices:
        overlap_start = max(start, start_time)
        overlap_end = min(end, end_time)
        duration = overlap_end - overlap_start
        total_price += price * duration
        total_duration += duration

    return total_price / total_duration if total_duration > 0 else 0.0

def get_min_price(start_time, end_time):
    _maybe_fetch_prices()

    relevant_prices = [p for p in prices if p[1] >= start_time and p[0] <= end_time]
    if not relevant_prices:
        return 0.0

    return min(price for _, _, price in relevant_prices)

def get_max_price(start_time, end_time):
    _maybe_fetch_prices()

    relevant_prices = [p for p in prices if p[1] >= start_time and p[0] <= end_time]
    if not relevant_prices:
        return 0.0

    return max(price for _, _, price in relevant_prices)

def get_low_price_intervals(
    start_time: float,
    end_time: float,
    fraction: float,
) -> list[tuple[float, float]]:
    """
    Return time intervals containing the n fraction of cheapest prices.

    Args:
        prices:
            List of tuples (start_timestamp, end_timestamp, price).
        fraction:
            Fraction of the cheapest price intervals to include.
            0.0 returns an empty list.
            1.0 returns the entire time range.

    Returns:
        A list of tuples (start_timestamp, end_timestamp) intervals.
        Consecutive selected intervals are merged.
    """

    _maybe_fetch_prices()

    # Filter prices to the requested time range
    _prices = [p for p in prices if p[1] >= start_time and p[0] <= end_time]
    #print(_prices)

    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0.0 and 1.0")

    if not _prices or fraction == 0.0:
        return []

    if fraction == 1.0:
        return [(_prices[0][0], _prices[-1][1])]

    # Sort price intervals from cheapest to most expensive.
    sorted_prices = sorted(_prices, key=lambda x: x[2])

    # Number of intervals to select.
    count = max(1, int(len(_prices) * fraction))

    selected = sorted_prices[:count]

    # Sort selected intervals back into chronological order.
    selected.sort(key=lambda x: x[0])

    # Merge consecutive intervals.
    intervals = []

    for start, end, _ in selected:
        if not intervals or (start - 0.1) > intervals[-1][1]:
            intervals.append((start, end))
        else:
            intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))

    return intervals

if __name__ == "__main__":
    now = time.time()
    price = get_price_at(now)
    print(f"Current price: {price}")
