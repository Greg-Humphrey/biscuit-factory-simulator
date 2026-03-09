# ==========================================================
# QUALITY ENGINE
# ----------------------------------------------------------
# This file defines all available quality systems and their
# financial impact.
#
# It is responsible for:
# - Storing quality system options (QC, QA, TQM)
# - Returning monthly running costs
# - Returning initial setup costs
# - Validating whether a quality system is valid
#
# Other engines use this file:
# - decision_engine validates student quality selections
# - simulation_engine applies monthly and change costs
# - production_process may reference quality helpers
#
# This file contains no simulation logic.
# It is purely a data + lookup engine.
# ==========================================================


# ----------------------------------------------------------
# QUALITY SYSTEM DEFINITIONS
# Each system has:
# - monthly_cost  → recurring operational cost
# - initial_cost  → setup cost charged when switching
# ----------------------------------------------------------

quality_options = {
    "qc": {
        "monthly_cost": 1500,
        "initial_cost": 0
    },
    "qa": {
        "monthly_cost": 1500,
        "initial_cost": 10000
    },
    "tqm": {
        "monthly_cost": 0,
        "initial_cost": 20000
    }
}


# ----------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------

def is_valid_quality_option(option_name):
    # Returns True if the option exists
    return option_name in quality_options


# ----------------------------------------------------------
# COST LOOKUPS
# ----------------------------------------------------------

def get_monthly_quality_cost(option_name):
    # Returns recurring monthly cost
    return quality_options[option_name]["monthly_cost"]


def get_initial_quality_cost(option_name):
    # Returns one-off setup cost
    return quality_options[option_name]["initial_cost"]
