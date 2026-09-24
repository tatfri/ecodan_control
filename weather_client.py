import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import bisect

import config

FMI_ENDPOINT = "https://opendata.fmi.fi/wfs"

STORED_QUERY = (
    "fmi::forecast::edited::weather::scandinavia::point::timevaluepair"
)

temperature = None

def clear():
    global temperature
    temperature = None

def fetch_temperature_forecast(place: str) -> list[tuple[float, float]]:
    print("Fetching temperature forecast...")

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "getFeature",
        "storedquery_id": STORED_QUERY,
        "place": place,
        "parameters": "temperature",
        "timestep": "60",
    }

    url = FMI_ENDPOINT + "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "EcodanController/1.0"},
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    result = []

    timestamp = None
    temperature = None

    for member in root.iter():
        if member.tag.endswith("waterml/2.0}time"):
            timestamp = member.text

        elif member.tag.endswith("waterml/2.0}value"):
            temperature = member.text

        if timestamp is not None and temperature is not None:
            dt = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )

            result.append((
                dt.timestamp(),
                float(temperature),
            ))

            timestamp = None
            temperature = None

    return result

def _maybe_fetch_temperature():
    global temperature
    if temperature is None:
        temperature = fetch_temperature_forecast(config.LOCATION)

def get_temperature_forecast(timestamp: float) -> float:
    _maybe_fetch_temperature()

    # Temperatures are assumed to be sorted by start time so we can search by bisecting
    i = bisect.bisect_right(temperature, (timestamp, float('inf')))

    if i:
        start_timestamp, temp = temperature[i-1]
        if start_timestamp <= timestamp:
            return temp

    _, temp = temperature[0]
    return temp

def _get_relevant_temperatures(start_time: float, end_time: float) -> list[float]:
    _maybe_fetch_temperature()

    return [
        temp for ts, temp in temperature
        if start_time <= ts <= end_time
    ]

def get_average_temperature(start_time: float, end_time: float) -> float:
    relevant_temperatures = _get_relevant_temperatures(start_time, end_time)

    if not relevant_temperatures:
        return get_temperature_forecast(start_time)

    return sum(relevant_temperatures) / len(relevant_temperatures)

def get_min_temperature(start_time: float, end_time: float) -> float:
    relevant_temperatures = _get_relevant_temperatures(start_time, end_time)

    if not relevant_temperatures:
        return get_temperature_forecast(start_time)

    return min(relevant_temperatures)

def get_max_temperature(start_time: float, end_time: float) -> float:
    relevant_temperatures = _get_relevant_temperatures(start_time, end_time)

    if not relevant_temperatures:
        return get_temperature_forecast(start_time)

    return max(relevant_temperatures)

if __name__ == "__main__":
    now = time.time() + 3600 * 12
    forecast = get_temperature_forecast(now)
    print(f"Current temperature forecast: {forecast} °C")