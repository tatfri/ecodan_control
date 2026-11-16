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

def get_temperature_setpoint(now):
    # Compare the price of the next MIN_HEATING_PERIOD_DURATION_SECONDS to all known future prices.
    estimated_price = estimate_heating_energy_price(now)
    if estimated_price < config.HEATING_ELECTRICITY_PRICE_LIMIT_EUROS * 100:
        return config.INITIAL_INDOOR_TEMPERATURE, None

    fraction = electricity_client.get_price_fraction(now, config.MIN_HEATING_PERIOD_DURATION_SECONDS)
    if fraction is None:
        return config.INITIAL_INDOOR_TEMPERATURE, None

    return get_temperature_setpoint_for_fraction(fraction), fraction

def get_dhw_start_time_and_clear_caches(start_time):
    weather_client.clear()
    electricity_client.clear()
    return get_dhw_heating_start_time(start_time)

def print_summary(start_time, dhw_heating_start_time):
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
    print("--------------------------------------------------")


if __name__ == "__main__":
    start_time = int(time.time())

    dhw_heating_start_time = get_dhw_start_time_and_clear_caches(start_time)
    print_summary(start_time, dhw_heating_start_time)

    setpoint, fraction = get_temperature_setpoint(start_time)
    print(f"Current price fraction: {fraction}, temperature setpoint: {setpoint}")
