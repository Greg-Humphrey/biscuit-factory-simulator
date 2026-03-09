# ==========================================================
# SCENARIO ENGINE
# ----------------------------------------------------------
# This file defines external events that affect the factory
# each month.
#
# It is responsible for:
# - Defining a neutral default scenario template
# - Defining month-specific overrides
# - Returning a complete scenario object for a given month
#
# The simulation_engine requests a scenario every month
# and applies its multipliers and costs during calculations.
#
# Important:
# We use deepcopy to avoid modifying the default template.
# ==========================================================


# ----------------------------------------------------------
# DEFAULT SCENARIO TEMPLATE
# This defines every possible scenario variable.
# Monthly scenarios override only what they change.
# ----------------------------------------------------------

DEFAULT_SCENARIO = {
    "name": "Just another month of biscuit baking",

    "scrap_rate": {
        "qc": 0.05,
        "qa": 0.03,
        "tqm": 0.01
    },

    "ingredient_multiplier": 1,
    "shipping_multiplier": 1,
    "sales_price_multiplier": 1,
    "demand_multiplier": 1,
    "extra_fixed_cost": 0,
    "machine_breakdown": 0,
    "employee_strike": 0
}
