import time

import config
import weather_client
import electricity_client

ESTIMATION_STEP_DURATION_SECONDS = 15 * 60 # 15 minutes
ESTIMATION_DURATION_SECONDS = 24 * 60 * 60 # 24 hours

BUILDING_ENERGY_LOSS_KW_PER_K = config.BUILDING_ENERGY_LOSS_KW_PER_K_PER_M2 * config.BUILDING_HEATED_FLOOR_AREA_M2

def interpolate_cop(temperature):
    temperatures = sorted(config.TEMPERATURE_TO_COP.keys())
    if temperature <= temperatures[0]:
        return config.TEMPERATURE_TO_COP[temperatures[0]]
    if temperature >= temperatures[-1]:
        return config.TEMPERATURE_TO_COP[temperatures[-1]]

    for i in range(1, len(temperatures)):
        if temperature < temperatures[i]:
            t0 = temperatures[i - 1]
            t1 = temperatures[i]
            cop0 = config.TEMPERATURE_TO_COP[t0]
            cop1 = config.TEMPERATURE_TO_COP[t1]
            return cop0 + (cop1 - cop0) * (temperature - t0) / (t1 - t0)
    return config.TEMPERATURE_TO_COP[temperatures[-1]]

def get_temperature_setpoint_for_fraction(fraction):
    # Determine the temperature setpoint based on the fraction using the TEMPERATURE_ADJUSTMENT list from config
    for threshold, adjustment in config.TEMPERATURE_ADJUSTMENT:
        if fraction <= threshold:
            return config.INDOOR_TEMPERATURE_MIDDLE_POINT + adjustment
    return config.INDOOR_TEMPERATURE_MIDDLE_POINT + config.TEMPERATURE_ADJUSTMENT[-1][1]

def estimate_heating_energy_kwh(start_time):
    end_time = start_time + ESTIMATION_DURATION_SECONDS
    total_energy_kwh = 0.0

    current_time = start_time
    while current_time < end_time:
        current_time += ESTIMATION_STEP_DURATION_SECONDS

        outside_temperature = weather_client.get_temperature_forecast(current_time)

        # Estimate the heating energy for the current step
        temperature_difference = config.INITIAL_INDOOR_TEMPERATURE - outside_temperature
        cop = interpolate_cop(outside_temperature)
        step_heating_energy_kwh = BUILDING_ENERGY_LOSS_KW_PER_K * temperature_difference * (ESTIMATION_STEP_DURATION_SECONDS / 3600.0)
        step_input_energy_kwh = step_heating_energy_kwh / cop
        total_energy_kwh += step_input_energy_kwh

    return total_energy_kwh

def estimate_heating_energy_price(start_time):
    end_time = start_time + ESTIMATION_DURATION_SECONDS
    total_energy_kwh = estimate_heating_energy_kwh(start_time)
    average_price = electricity_client.get_average_price(start_time, end_time)
    return total_energy_kwh * average_price

def get_energy_price(power_consumed):
    period_length_hours = 1 / 60 # Default to 1 minute
    total_price_euro_cent = 0.0

    for i in range(len(power_consumed)):
        start_time, power_kwh = power_consumed[i]
        next_time, _ = power_consumed[i + 1] if i + 1 < len(power_consumed) else (None, None)

        if next_time is not None:
            period_length_hours = (next_time - start_time) / 3600.0

        price_euro_cent = electricity_client.get_price_at(start_time)
        total_price_euro_cent += power_kwh * price_euro_cent * period_length_hours

    return total_price_euro_cent

def get_dhw_heating_start_time(start_time):
    fraction = 0.0125
    fraction_step = 0.0125
    while fraction < 1.0:
        lowest_intervals = electricity_client.get_low_price_intervals(start_time, start_time + ESTIMATION_DURATION_SECONDS, fraction)

        # Find interval in which DHW_TANK_HEATING_PERIOD_DURATION_SECONDS can fit
        for start, end in lowest_intervals:
            if end - start >= config.DHW_TANK_HEATING_PERIOD_DURATION_SECONDS:
                return start

        fraction += fraction_step

    return None

def cut_interval(excluded_interval, intervals):
    if excluded_interval is None:
        return intervals

    result = []
    ex_start, ex_end = excluded_interval
    for start, end in intervals:
        if end <= ex_start or start >= ex_end:
            result.append((start, end))
        else:
            if start < ex_start:
                result.append((start, ex_start))
            if end > ex_end:
                result.append((ex_end, end))
    return result

def cut_intervals(excluded_intervals, intervals):
    result = intervals
    for excluded_interval in excluded_intervals:
        result = cut_interval(excluded_interval, result)
    return result

def join_intervals(intervals0, intervals1):
    result = []
    all_intervals = sorted(intervals0 + intervals1, key=lambda x: x[0])
    for interval in all_intervals:
        if not result:
            result.append(interval)
        else:
            last_start, last_end = result[-1]
            current_start, current_end = interval
            if current_start <= last_end:
                result[-1] = (last_start, max(last_end, current_end))
            else:
                result.append(interval)
    return result

def get_low_price_intervals(start_time, fraction):
    return electricity_client.get_low_price_intervals(start_time, start_time + ESTIMATION_DURATION_SECONDS, fraction)

def merge_short_intervals(original_intervals, min_interval_length):
    # If there are intervals that are shorter than minimun interval with their neighbors. Merge them with
    # either the previous or the next interval depending on which one has lower set temperature. Set the
    # merged interval's temperature to the lower one.

    intervals = original_intervals.copy()

    change_done = True
    while change_done:
        change_done = False
        i = 0
        while i < len(intervals):
            start, end, temperature_setpoint = intervals[i]
            if end - start < min_interval_length:
                change_done = True
                if i > 0 and i < len(intervals) - 1:
                    prev_start, prev_end, prev_temp = intervals[i - 1]
                    next_start, next_end, next_temp = intervals[i + 1]
                    if prev_temp < next_temp:
                        intervals[i - 1] = (prev_start, end, prev_temp)
                        del intervals[i]
                        i -= 1
                    else:
                        intervals[i + 1] = (start, next_end, next_temp)
                        del intervals[i]
                        i -= 1
                elif i > 0:
                    prev_start, prev_end, prev_temp = intervals[i - 1]
                    intervals[i - 1] = (prev_start, end, prev_temp)
                    del intervals[i]
                    i -= 1
                elif i < len(intervals) - 1:
                    next_start, next_end, next_temp = intervals[i + 1]
                    intervals[i + 1] = (start, next_end, next_temp)
                    del intervals[i]
                    i -= 1
            i += 1
    return intervals

def join_consecutive_intervals(intervals):
    joined_intervals = []
    for start, end, temperature_setpoint in intervals:
        if joined_intervals and joined_intervals[-1][1] == start and joined_intervals[-1][2] == temperature_setpoint:
            joined_intervals[-1] = (joined_intervals[-1][0], end, temperature_setpoint)
        else:
            joined_intervals.append((start, end, temperature_setpoint))
    return joined_intervals

def get_heating_periods(start_time, schedule_dhw_heating):
    weather_client.clear()
    electricity_client.clear()

    dwh_heating_start_time = None
    if schedule_dhw_heating:
        dwh_heating_start_time = get_dhw_heating_start_time(start_time)

    estimated_price = estimate_heating_energy_price(start_time)

    if (estimated_price < config.HEATING_ELECTRICITY_PRICE_LIMIT_EUROS * 100):
        return [(start_time, start_time + ESTIMATION_DURATION_SECONDS, config.INITIAL_INDOOR_TEMPERATURE)], dwh_heating_start_time

    all_intervals = []
    prev_intervals = []

    for i in range(5):
        fraction = (i + 1) * 0.20
        intervals = get_low_price_intervals(start_time, fraction)

        intervals = cut_intervals(prev_intervals, intervals)
        prev_intervals = join_intervals(prev_intervals, intervals)

        for start, end in intervals:
            # - 0.001 so that 0.6000000000000001 gets handled right
            all_intervals.append((start, end, get_temperature_setpoint_for_fraction(fraction - 0.001)))

    all_intervals = sorted(all_intervals, key=lambda x: x[0])

    # Join consecutive intervals with same temperature
    joined_intervals = join_consecutive_intervals(all_intervals)

    # Merge intervals that are shorter than the minimum heating period duration.
    joined_intervals = merge_short_intervals(joined_intervals, config.MIN_HEATING_PERIOD_DURATION_SECONDS)

    # Join again because the previous step may have created new consecutive intervals with the same temperature.
    joined_intervals = join_consecutive_intervals(joined_intervals)

    return joined_intervals, dwh_heating_start_time

def print_periods(start_time, periods, dhw_heating_start_time):
    end_time = start_time + ESTIMATION_DURATION_SECONDS
    min_temperature = weather_client.get_min_temperature(start_time, end_time)
    max_temperature = weather_client.get_max_temperature(start_time, end_time)
    avg_temperature = weather_client.get_average_temperature(start_time, end_time)

    min_price = electricity_client.get_min_price(start_time, end_time)
    max_price = electricity_client.get_max_price(start_time, end_time)
    avg_price = electricity_client.get_average_price(start_time, end_time)

    estimated_energy_kwh = estimate_heating_energy_kwh(start_time)
    estimated_price = estimate_heating_energy_price(start_time)

    print("--------------------------------------------------")
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
    print(f"End time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
    print(f"Min temperature: {min_temperature:.2f} °C")
    print(f"Max temperature: {max_temperature:.2f} °C")
    print(f"Average temperature: {avg_temperature:.2f} °C")
    print(f"Min price: {min_price:.2f} c/kWh")
    print(f"Max price: {max_price:.2f} c/kWh")
    print(f"Average price: {avg_price:.2f} c/kWh")
    print("")
    print(f"Estimated heating energy: {estimated_energy_kwh:.2f} kWh")
    print(f"Estimated heating energy price: {estimated_price:.2f} c")
    print("")
    print("DHW heating start:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(dhw_heating_start_time)))
    print("")
    for period in periods:
        start, stop, temperature_setpoint = period
        print("Heating period:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start)), "to", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stop)), "with temperature setpoint:", temperature_setpoint)
    print("--------------------------------------------------")


if __name__ == "__main__":
    import time

    #start_time = int(time.time()) - 12 * 60 * 60
    start_time = int(time.time())

    schedule_dhw_heating = True
    heating_periods, dhw_heating_start_time = get_heating_periods(start_time, schedule_dhw_heating)

    print_periods(start_time, heating_periods, dhw_heating_start_time)