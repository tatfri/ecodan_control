ECODAN_UART = "/dev/ttyAMA0"

# Middle point indoor temperature setpoint. Temperature setpoint sent to the heat pump will
# fluctuate +- 2 degrees celsius around the middle point.
#
# Note that this doesn't necessarily match the actual real indoor temperature. If the actual
# temperature tends to be too high or too low, you may need to adjust the middle point accordingly.
INDOOR_TEMPERATURE_MIDDLE_POINT = 18.0

# Default temperature setpoint used if electricity price API can't be accessed.
INITIAL_INDOOR_TEMPERATURE = 19.0

# Duration assumed to be needed to finish Domestic Hot Water (DHW) tank heating period.
# The algorithm will look for the cheapest time period at least this length to select when
# forced DWH heating will trigger. If DHW heating takes longer than this duration, the heating
# may continue into more expensive electricity price periods.
DHW_TANK_HEATING_PERIOD_DURATION_SECONDS = 20 * 60  # 20 minutes

# Time of the day when the estimation for the next 24h period will be updated.
# Finnish electricity market prices for the next day will be available around 14:00.
HEATING_PERIODS_UPDATE_TIME_OF_DAY = "15:00"

# -----------------------
# Settings below only affect estimation of heating energy needed, they do not affect the control,
# except that INDOOR TEMPERATURE is used for the whole 24h period if the estimated heating cost is below
# the threshold below.
# -----------------------

# If electricity price estimated to be needed for heating without optimization is below this limit,
# skip the optimization to avoid unnecessary fluctuations in room temperature.
HEATING_ELECTRICITY_PRICE_LIMIT_EUROS = 0.25

# Location passed to Finnish Meteorological Institute (FMI) API for fetching weather forecast.
LOCATION = "Lahti"

# COP for Ecodan SUZ-SHWM60VAH at when heating water to 35 degrees Celsius
# Source: MITSUBISHI ELECTRIC Ecodan Renewable Heating Technology DATA BOOK Vol.5.8 R32
TEMPERATURE_TO_COP = {
    -25: 1.73,
    -20: 1.87,
    -15: 2.09,
    -10: 2.38,
    -7:  2.87,
    2: 3.47,
    7: 4.95,
    12: 5.73,
    15: 6.49,
    20: 7.98
}

# Used for estimating the building's heating demand.
BUILDING_HEATED_FLOOR_AREA_M2 = 135

# Building heating loss coefficient (kW per K per m2).
# This value should be good for a modern (>2010) Finnish single family home. Consult AI
# for values to use with building of different type and age.
BUILDING_ENERGY_LOSS_KW_PER_K_PER_M2 = 0.0009
