# ==========================================================
# FACTORY ENGINE
# ----------------------------------------------------------
# This file is responsible for building and validating the
# physical factory structure.
#
# It handles:
# - Factory creation
# - Space calculations
# - Adding production lines
# - Adding fixtures (doors, windows)
# - Floor slab logic
# - Roof panel logic
# - Wall coverage logic
# - Construction cost calculations
#
# It does NOT handle:
# - Monthly operations
# - Revenue or profit
# - Student decision validation
#
# Other engines that depend on this:
# - decision_engine (for building factory during setup)
# - simulation_engine (for build cost calculation)
# ==========================================================

import production_process as pp
import math


# ----------------------------------------------------------
# CONSTRUCTION COST PARAMETERS
# ----------------------------------------------------------

FLOOR_SLAB_LENGTH = 10
FLOOR_SLAB_WIDTH = 5
FLOOR_SLAB_COST = 75

ROOF_PANEL_AREA = 1  # Each panel covers 1m²
ROOF_PANEL_COST = 40

INDUSTRIAL_DOOR_COST = 500
PEDESTRIAN_DOOR_COST = 200
WINDOW_COST = 100

ELECTRICS_COST_PER_M2 = 200
PLUMBING_COST_PER_M2 = 150

MIN_REMAINING_SPACE_PERCENT = 50


# ----------------------------------------------------------
# WALL BLOCK DEFINITIONS
# ----------------------------------------------------------

wall_blocks = {
    "small": {"width_m": 1, "length_m": 1, "cost": 10},
    "medium": {"width_m": 3, "length_m": 1, "cost": 30},
    "large": {"width_m": 5, "length_m": 1, "cost": 50}
}


# ----------------------------------------------------------
# FIXTURE DEFINITIONS
# ----------------------------------------------------------

fixtures = {
    "industrial_door": {"width_m": 5, "length_m": 5},
    "pedestrian_door": {"width_m": 2, "length_m": 2},
    "window": {"width_m": 1, "length_m": 1}
}


# ==========================================================
# FACTORY CREATION
# ==========================================================

def create_factory(length_m, width_m):

    total_space = length_m * width_m

    return {
        "length_m": length_m,
        "width_m": width_m,
        "total_space_m2": total_space,
        "quality_system": None,
        "lines": [],
        "fixtures": {
            "industrial_door": 0,
            "pedestrian_door": 0,
            "window": 0
        },
        "wall_blocks_used": {
            "small": 0,
            "medium": 0,
            "large": 0
        },
        "floor_slabs_purchased": 0,
        "roof_panels_purchased": 0
    }


# ==========================================================
# SPACE CALCULATIONS
# ==========================================================

def calculate_used_space(factory):

    total_used = 0

    # Production lines
    for line in factory["lines"]:
        total_used += pp.get_floor_area(line["process_type"])

    # Fixtures
    for fixture, count in factory["fixtures"].items():
        total_used += get_fixture_area(fixture) * count

    return total_used


def calculate_remaining_space(factory):
    return factory["total_space_m2"] - calculate_used_space(factory)


# ==========================================================
# PRODUCTION LINES
# ==========================================================

def add_production_line(factory, process_name):

    required_space = pp.get_floor_area(process_name)
    remaining_space = calculate_remaining_space(factory)

    if required_space > remaining_space:
        return False

    factory["lines"].append({
        "process_type": process_name,
        "current_biscuit": None,
        "batches_this_month": 0,
        "changeovers_this_month": 0
    })

    return True


# ==========================================================
# FIXTURES
# ==========================================================

def get_fixture_area(fixture_name):
    width = fixtures[fixture_name]["width_m"]
    length = fixtures[fixture_name]["length_m"]
    return width * length


def add_fixture(factory, fixture_name, quantity=1):

    if fixture_name not in fixtures:
        return False

    if not isinstance(quantity, int) or quantity < 0:
        return False

    required_space = get_fixture_area(fixture_name) * quantity

    if required_space > calculate_remaining_space(factory):
        return False

    factory["fixtures"][fixture_name] += quantity
    return True


# ==========================================================
# FLOOR LOGIC
# ==========================================================

def slabs_required(factory):
    slab_area = FLOOR_SLAB_LENGTH * FLOOR_SLAB_WIDTH
    return math.ceil(factory["total_space_m2"] / slab_area)


def add_floor_slabs(factory, quantity):

    if not isinstance(quantity, int) or quantity < 0:
        return False

    factory["floor_slabs_purchased"] += quantity
    return True


def floors_complete(factory):
    return factory["floor_slabs_purchased"] >= slabs_required(factory)


def calculate_floor_cost(factory):
    return factory["floor_slabs_purchased"] * FLOOR_SLAB_COST


# ==========================================================
# ROOF LOGIC
# ==========================================================

def panels_required(factory):
    return math.ceil(factory["total_space_m2"] / ROOF_PANEL_AREA)


def calculate_required_roof_panels(factory):
    return int(factory["total_space_m2"])


def add_roof_panels(factory, quantity):

    if not isinstance(quantity, int) or quantity < 0:
        return False

    factory["roof_panels_purchased"] += quantity
    return True


def roof_complete(factory):
    return factory["roof_panels_purchased"] >= panels_required(factory)


def calculate_roof_cost(factory):
    return factory["roof_panels_purchased"] * ROOF_PANEL_COST


# ==========================================================
# FIXTURE COST
# ==========================================================

def calculate_fixture_cost(factory):

    total = 0
    total += factory["fixtures"]["industrial_door"] * INDUSTRIAL_DOOR_COST
    total += factory["fixtures"]["pedestrian_door"] * PEDESTRIAN_DOOR_COST
    total += factory["fixtures"]["window"] * WINDOW_COST

    return total


# ==========================================================
# UTILITIES COST
# ==========================================================

def calculate_utilities_cost(factory):

    area = factory["total_space_m2"]

    electrics = area * ELECTRICS_COST_PER_M2
    plumbing = area * PLUMBING_COST_PER_M2

    return electrics + plumbing


# ==========================================================
# WALL LOGIC
# ==========================================================

def calculate_required_wall_length(factory):
    perimeter = 2 * (factory["length_m"] + factory["width_m"])
    return perimeter + 4  # structural reinforcement


def add_wall_blocks(factory, block_type, quantity):

    if block_type not in wall_blocks:
        return False

    if not isinstance(quantity, int) or quantity < 0:
        return False

    factory["wall_blocks_used"][block_type] += quantity
    return True


def calculate_wall_coverage(factory):

    total = 0

    for block_type, quantity in factory["wall_blocks_used"].items():
        total += wall_blocks[block_type]["width_m"] * quantity

    return total


def walls_complete(factory):
    return calculate_wall_coverage(factory) >= calculate_required_wall_length(factory)


def calculate_wall_cost(factory):

    total = 0

    for block_type, quantity in factory["wall_blocks_used"].items():
        total += quantity * wall_blocks[block_type]["cost"]

    return total


# ==========================================================
# TOTAL BUILD COST
# ==========================================================

def calculate_total_build_cost(factory):

    if not walls_complete(factory):
        return None

    return (
        calculate_floor_cost(factory)
        + calculate_roof_cost(factory)
        + calculate_fixture_cost(factory)
        + calculate_utilities_cost(factory)
        + calculate_wall_cost(factory)
    )


# ==========================================================
# VALIDATION
# ==========================================================

def validate_factory(factory):

    if not walls_complete(factory):
        return False, "Wall coverage incomplete."

    if not floors_complete(factory):
        return False, "Insufficient floor slabs."

    if not roof_complete(factory):
        return False, "Insufficient roof panels."

    return True, "Factory valid."
