# ==========================================================
# PRODUCTION PROCESS ENGINE
# ----------------------------------------------------------
# This file defines all production process types (job, batch,
# cell, flow) and calculates costs associated with them.
#
# It is responsible for:
# - Capital cost calculations
# - Labour cost calculations
# - Changeover costs
# - Shipping cost calculation
# - Process output validation
# - Floor space requirements for each process
#
# Other engines depend on this:
# - simulation_engine uses it for operational cost calculations
# - factory_engine uses it for floor space requirements
# - decision_engine uses it to validate output limits
# ==========================================================

import quality_engine as qe


# ----------------------------------------------------------
# UNIVERSAL COST SETTINGS
# These define cost scaling rules used across all processes
# ----------------------------------------------------------

CAPITAL_COST_PER_10_PERCENT = 10000
LABOUR_COST_PER_10_PERCENT = 1500
UTILITIES_COST_PER_10_PERCENT = 100

SHIPPING_COST_BASE = 5000
SHIPPING_VOLUME_BASE = 50000  # Units covered by base shipping cost

CHANGEOVER_COST_PER_10_PERCENT = 2500


# ----------------------------------------------------------
# PROCESS DEFINITIONS
# Each process defines:
# - Output limits
# - Capital vs labour intensity
# - Physical floor size requirements
# ----------------------------------------------------------

processes = {
    "job": {
        "min_units_per_month": 100,
        "max_units_per_month": 1000,
        "capital_intensity": 20,
        "labour_intensity": 80,
        "width_m": 3,
        "length_m": 3
    },
    "batch": {
        "min_units_per_month": 10000,
        "max_units_per_month": 100000,
        "capital_intensity": 50,
        "labour_intensity": 50,
        "width_m": 5,
        "length_m": 5
    },
    "cell": {
        "min_units_per_month": 100000,
        "max_units_per_month": 500000,
        "capital_intensity": 70,
        "labour_intensity": 30,
        "width_m": 4,
        "length_m": 4
    },
    "flow": {
        "min_units_per_month": 500000,
        "max_units_per_month": 1000000,
        "capital_intensity": 90,
        "labour_intensity": 10,
        "width_m": 1,
        "length_m": 8
    }
}


# ----------------------------------------------------------
# OUTPUT VALIDATION
# Ensures total line production stays within allowed limits
# ----------------------------------------------------------

def get_process_limits(process_name):
    return processes[process_name]


def is_output_valid(process_name, planned_units):
    process = processes[process_name]

    min_units = process["min_units_per_month"]
    max_units = process["max_units_per_month"]

    if planned_units < min_units:
        return False

    if max_units is not None and planned_units > max_units:
        return False

    return True


# ----------------------------------------------------------
# COST CALCULATIONS
# ----------------------------------------------------------

def calculate_capital_cost(process_name):
    percent = processes[process_name]["capital_intensity"]
    blocks = percent / 10
    return blocks * CAPITAL_COST_PER_10_PERCENT


def calculate_labour_cost(process_name):
    percent = processes[process_name]["labour_intensity"]
    blocks = percent / 10
    return blocks * LABOUR_COST_PER_10_PERCENT

def calculate_monthly_utilities_cost(process_name):
    percent = processes[process_name]["capital_intensity"]
    blocks = percent / 10
    return blocks * UTILITIES_COST_PER_10_PERCENT

def get_labour_intensity(process_name):
    return processes[process_name]["labour_intensity"]


def calculate_changeover_cost(process_name):
    # Changeover cost scales with capital intensity
    capital_intensity = processes[process_name]["capital_intensity"]
    blocks = capital_intensity / 10
    return blocks * CHANGEOVER_COST_PER_10_PERCENT


def calculate_shipping_cost(units_shipped):
    # Shipping cost scales linearly with units shipped
    cost_per_unit = SHIPPING_COST_BASE / SHIPPING_VOLUME_BASE
    return units_shipped * cost_per_unit


# ----------------------------------------------------------
# FLOOR SPACE REQUIREMENTS
# Used by factory_engine for layout validation
# ----------------------------------------------------------

def get_floor_area(process_name):
    width = processes[process_name]["width_m"]
    length = processes[process_name]["length_m"]
    return width * length


# ----------------------------------------------------------
# QUALITY SYSTEM HELPERS
# These act as pass-through helpers to quality_engine
# ----------------------------------------------------------

def set_quality_system(factory, option_name):
    if not qe.is_valid_quality_option(option_name):
        return False
    factory["quality_system"] = option_name
    return True


def calculate_quality_initial_cost(quality_option):
    if quality_option is None:
        return 0
    return qe.get_initial_quality_cost(quality_option)


def calculate_quality_monthly_cost(quality_option):
    if quality_option is None:
        return 0
    return qe.get_monthly_quality_cost(quality_option)
