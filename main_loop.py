import time

from ecodan_protocol import client
from heating_estimation import get_dhw_start_time_and_clear_caches, get_temperature_setpoint, print_summary, get_energy_price
import electricity_client
import config

STATUS_FETCH_INTERVAL_S = 60

last_status_fetched = 0
prev_hour = -1
indoor_heating_input_power = []
dhw_heating_input_power = []
last_setpoint_update_slot = None
dhw_heating_start_time = None
temperature_setpoint = 0.0
logfile = open("heating_log.txt", "a")

def get_kwh(power_consumed):
    total_kwh = 0.0
    for _, power_kw in power_consumed:
        total_kwh += power_kw * (STATUS_FETCH_INTERVAL_S / 3600.0)
    return total_kwh

def update_dhw_heating_start_time(now):
    global dhw_heating_start_time

    total_indoor_heating_power_kwh = get_kwh(indoor_heating_input_power)
    total_dhw_heating_power_kwh = get_kwh(dhw_heating_input_power)
    indoor_heating_price = get_energy_price(indoor_heating_input_power)
    dhw_heating_price = get_energy_price(dhw_heating_input_power)

    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}, Updating DHW heating start time and electricity prices")
    print("--------------------------------------------------")
    print(f"Indoor heating power: {total_indoor_heating_power_kwh:.2f} kWh")
    print(f"Indoor heating price: {indoor_heating_price:.2f} c")
    print(f"DHW heating power: {total_dhw_heating_power_kwh:.2f} kWh")
    print(f"DHW heating price: {dhw_heating_price:.2f} c")
    print(f"Total heating power: {total_indoor_heating_power_kwh + total_dhw_heating_power_kwh:.2f} kWh")
    print(f"Total heating price: {indoor_heating_price + dhw_heating_price:.2f} c")

    indoor_heating_input_power.clear()
    dhw_heating_input_power.clear()

    dhw_heating_start_time = get_dhw_start_time_and_clear_caches(now)
    print_summary(now, dhw_heating_start_time)

def fetch_status(ecodan_client,now):
    global last_status_fetched

    last_status_fetched = now

    op_mode = ecodan_client.get_operation_mode()
    power = ecodan_client.get_heater_power()
    flow_temps = ecodan_client.get_water_flow_temperatures()

    op_mode_desc = op_mode["data"]["operation_mode_desc"]
    input_power_kw_band = power["data"]["input_power_kw_band"]
    output_heater_power_kw = power["data"]["heater_power_kw"]
    dhw_temp = flow_temps["data"]["hot_water_temp"]

    print(f"Operation mode: {op_mode_desc}, input power: {input_power_kw_band}, DHW temp: {dhw_temp}, heater power: {output_heater_power_kw}")

    current_indoor_heating_input_power = 0
    current_dhw_heating_input_power = 0

    if op_mode_desc == "hot water":
        current_dhw_heating_input_power = input_power_kw_band
    elif op_mode_desc == "heating":
        current_indoor_heating_input_power = input_power_kw_band

    indoor_heating_input_power.append((now, current_indoor_heating_input_power))
    dhw_heating_input_power.append((now, current_dhw_heating_input_power))

    electricity_price = electricity_client.get_price_at(now)

    logfile.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} indoor {current_indoor_heating_input_power} dhw {current_dhw_heating_input_power} dhw_temp {dhw_temp} output {output_heater_power_kw} electricity_price {electricity_price} set_temp {temperature_setpoint}\n")
    logfile.flush()

def should_update_dhw_heating():
    global prev_hour

    update_needed = True
    if prev_hour != -1:
        current_hour = int(time.strftime("%H"))
        update_needed = current_hour != prev_hour and time.strftime("%H:%M") == config.DHW_HEATING_UPDATE_TIME_OF_DAY
    prev_hour = int(time.strftime("%H"))
    return update_needed

def should_fetch_status():
    global last_status_fetched

    current_time = time.time()
    return current_time - last_status_fetched >= STATUS_FETCH_INTERVAL_S

def maybe_start_dhw_heating(ecodan_client, now):
    global dhw_heating_start_time

    if dhw_heating_start_time is None:
        return

    if now > dhw_heating_start_time:
        dhw_heating_start_time = None

        print(f"Starting DHW heating!")
        ecodan_client.set_hot_water_and_holiday(dhw_force=True)

def maybe_set_temperature_setpoint(ecodan_client, now):
    global last_setpoint_update_slot
    global temperature_setpoint

    # Update at the start of every MIN_HEATING_PERIOD_DURATION_SECONDS slot aligned to wall clock time.
    slot = int(now // config.MIN_HEATING_PERIOD_DURATION_SECONDS)
    if slot == last_setpoint_update_slot:
        return
    last_setpoint_update_slot = slot

    new_setpoint, fraction = get_temperature_setpoint(now)
    print(f"Price fraction: {fraction:.2f}, setting temperature setpoint to {new_setpoint}.")
    if new_setpoint != temperature_setpoint:
        temperature_setpoint = new_setpoint
        ecodan_client.set_options(z1_setpoint=temperature_setpoint)

def main_loop(ecodan_client):
    while True:
        now = time.time()
        next_tick = time.perf_counter() + 1

        if should_update_dhw_heating():
            update_dhw_heating_start_time(now)

        elif should_fetch_status():
            fetch_status(ecodan_client, now)

        maybe_start_dhw_heating(ecodan_client, now)
        maybe_set_temperature_setpoint(ecodan_client, now)

        sleep_duration = max(0, next_tick - time.perf_counter())
        time.sleep(sleep_duration)

if __name__ == "__main__":
    with client.EcodanClient(config.ECODAN_UART) as ecodan_client:
        ecodan_client.connect()
        ecodan_client.set_options(z1_setpoint=config.INITIAL_INDOOR_TEMPERATURE)

        main_loop(ecodan_client)
