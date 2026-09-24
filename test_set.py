
from ecodan_protocol import EcodanClient
import config

with EcodanClient(config.ECODAN_UART) as client:
    client.connect()
    print("connection successful!")

    client.set_options(
        z1_setpoint=21.0
    )


