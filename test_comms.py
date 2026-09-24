
from ecodan_protocol import EcodanClient
import config

with EcodanClient(config.ECODAN_UART) as client:
     client.connect()
     print("connection successful!")

     print("Zone setpoints")
     print(client.get_zone_setpoints())
     print("Date & time")
     print(client.get_date_time())
     print("Output power")
     print(client.get_heater_power())
     print("Error codes")
     print(client.get_error_codes())
     print("Heat source")
     print(client.get_heat_source())
     print("Zone and outside temps")
     print(client.get_zone_and_outside_temperatures())
     print("Water flow temps")
     print(client.get_water_flow_temperatures())
     print("Run hours")
     print(client.get_run_hours())
     print("Get pump status")
     print(client.get_pump_status())
     print("Operational mode")
     print(client.get_operation_mode())
     print("Get zone temperatures")
     print(client.get_zone_temperatures())
     print("Get consumed energy")
     print(client.get_consumed_energy())
     print("Get delivered energy")
     print(client.get_delivered_energy())

