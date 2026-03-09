# ==========================================================
# DECISION ENGINE
# ==========================================================
# This file acts as the validation and control layer between
# student decisions and the simulation engine.
#
# It is responsible for:
# - Creating the initial simulation from setup decisions
# - Validating all student inputs (factory + monthly decisions)
# - Enforcing setup vs operating phase rules
# - Validating production plans and quality selections
#
# It does NOT:
# - Perform financial calculations
# - Run monthly operations
# - Calculate profit or costs
#
# Other engines that depend on this:
# - Simulation_manager uses this to validate all team inputs
# - simulation_engine assumes all decisions are already valid
# - factory_engine is used to physically build the factory
# ==========================================================

import production_process as pp
import quality_engine as qe
import factory_engine as fe
import simulation_engine as sim
import ingredients_engine as ie


# ==========================================================
# APPLY STUDENT DECISIONS
# ==========================================================
# Applies and validates student decisions depending on phase
# ==========================================================

def apply_student_decisions(state, decisions):

    factory = state["factory"]
    phase = state.get("phase", "setup")

    # --------------------------------------------------
    # PHASE CONTROL RULES
    # --------------------------------------------------

    # During setup phase, a production plan must be provided
    if phase == "setup" and "production_plan" not in decisions:
        return False, "Production plan required during setup phase."

    # Once operating, factory structure cannot be modified
    if phase == "operating" and "factory" in decisions:
        return False, "Factory structure cannot be modified after setup."

    # --------------------------------------------------
    # QUALITY SYSTEM VALIDATION
    # --------------------------------------------------

    if "quality_system" in decisions:
        quality_option = decisions["quality_system"]

        if not qe.is_valid_quality_option(quality_option):
            return False, "Invalid quality system selected."

    # --------------------------------------------------
    # PRODUCTION PLAN VALIDATION
    # --------------------------------------------------

    if "production_plan" in decisions:

        production_plan = decisions["production_plan"]

        # Production plan must be dictionary of line_index → runs
        if not isinstance(production_plan, dict):
            return False, "Production plan must be a dictionary."

        # During setup, plan cannot be empty
        if phase == "setup" and not production_plan:
            return False, "Production plan cannot be empty during setup."

        valid_biscuits = ie.get_all_biscuit_names()

        for line_index, runs in production_plan.items():

            # Validate line index
            if not isinstance(line_index, int):
                return False, "Line index must be an integer."

            if line_index < 0 or line_index >= len(factory["lines"]):
                return False, f"Line {line_index} does not exist."

            # Each line must contain a list of production runs
            if not isinstance(runs, list):
                return False, f"Production plan for line {line_index} must be a list."

            process_type = factory["lines"][line_index]["process_type"]
            total_units = 0

            for run in runs:

                # Each run must be dictionary
                if not isinstance(run, dict):
                    return False, "Each production run must be a dictionary."

                if "biscuit" not in run or "units" not in run:
                    return False, "Each run must include 'biscuit' and 'units'."

                biscuit = run["biscuit"]
                units = run["units"]

                # Validate biscuit name
                if biscuit not in valid_biscuits:
                    return False, f"Invalid biscuit: {biscuit}"

                # Units must be positive number
                if not isinstance(units, (int, float)) or units <= 0:
                    return False, f"Invalid units for {biscuit}"

                total_units += units

            # Validate total output against process limits
            if not pp.is_output_valid(process_type, total_units):
                return False, (
                    f"{total_units} total units invalid for {process_type} process."
                )

    # --------------------------------------------------
    # APPLY VALIDATED CHANGES
    # --------------------------------------------------

    if "quality_system" in decisions:
        factory["quality_system"] = decisions["quality_system"]

    if "production_plan" in decisions:
        state["production_plan"] = decisions["production_plan"]

    return True, "Decisions applied successfully."


# ==========================================================
# INITIAL FACTORY CREATION
# ==========================================================
# Builds and validates factory from student setup input
# ==========================================================

def create_simulation_from_initial_decisions(decisions):

    try:
        errors = []
        # --------------------------------------------------
        # BASIC SETUP EXTRACTION
        # --------------------------------------------------

        factory_data = decisions["factory"]
        starting_cash = decisions["starting_cash"]

        length = factory_data["length_m"]
        width = factory_data["width_m"]

        factory = fe.create_factory(length, width)

        # --------------------------------------------------
        # WALL BLOCKS
        # --------------------------------------------------

        for block_type, quantity in factory_data["wall_blocks"].items():
            fe.add_wall_blocks(factory, block_type, quantity)

        # --------------------------------------------------
        # FIXTURES
        # --------------------------------------------------

        for fixture_name, quantity in factory_data["fixtures"].items():
            fe.add_fixture(factory, fixture_name, quantity)

        # --------------------------------------------------
        # DOOR VALIDATION
        # --------------------------------------------------

        industrial_doors = factory_data["fixtures"].get("industrial_door", 0)
        pedestrian_doors = factory_data["fixtures"].get("pedestrian_door", 0)

        if industrial_doors < 1 or pedestrian_doors < 1:
            errors.append("doors")

        # --------------------------------------------------
        # PRODUCTION LINES
        # --------------------------------------------------

        for process_type in factory_data["production_lines"]:
            success = fe.add_production_line(factory, process_type)

            if not success:
                return None, f"Not enough space for production line: {process_type}"

        # --------------------------------------------------
        # PRODUCTION LINE VALIDATION
        # --------------------------------------------------

        if len(factory["lines"]) < 1:
            errors.append("lines")

        # --------------------------------------------------
        # FACTORY SPACE VALIDATION
        # --------------------------------------------------

        remaining_space = fe.calculate_remaining_space(factory)
        total_space = factory["total_space_m2"]

        remaining_percent = (remaining_space / total_space) * 100

        if remaining_percent < fe.MIN_REMAINING_SPACE_PERCENT:
            errors.append("space")

        # --------------------------------------------------
        # QUALITY SYSTEM
        # --------------------------------------------------

        quality_option = factory_data.get("quality_system")

        if not quality_option:
            errors.append("quality")

        elif not qe.is_valid_quality_option(quality_option):
            errors.append("quality")

        else:
            factory["quality_system"] = quality_option

        # --------------------------------------------------
        # FLOOR SLABS VALIDATION
        # --------------------------------------------------

        if "floor_slabs" not in factory_data:
            errors.append("floor_slabs")
        else:

            floor_slabs = factory_data["floor_slabs"]

            if not isinstance(floor_slabs, int) or floor_slabs < 0:
                errors.append("floor_slabs")

            else:
                required_slabs = fe.slabs_required(factory)

                if floor_slabs < required_slabs:
                    errors.append("floor_slabs")

                fe.add_floor_slabs(factory, floor_slabs)

        # --------------------------------------------------
        # ROOF PANEL VALIDATION
        # --------------------------------------------------

        if "roof_panels" not in factory_data:
            errors.append("roof_panels")

        else:

            roof_panels = factory_data["roof_panels"]

            if not isinstance(roof_panels, int) or roof_panels < 0:
                errors.append("roof_panels")

            else:
                required_roof = fe.calculate_required_roof_panels(factory)

                if roof_panels < required_roof:
                    errors.append("roof_panels")

                fe.add_roof_panels(factory, roof_panels)

        # --------------------------------------------------
        # WALL VALIDATION
        # --------------------------------------------------

        if not fe.walls_complete(factory):
            errors.append("wall_blocks")

        # --------------------------------------------------
        # CAPITAL VALIDATION
        # --------------------------------------------------

        fe.calculate_total_build_cost(factory)

        total_cost = fe.calculate_total_build_cost(factory)

        # Factory build incomplete (e.g. walls not finished)
        if total_cost is None:
            errors.append("wall_blocks")

        # Only check capital if build cost exists
        elif total_cost > starting_cash:
            errors.append("capital")


        # --------------------------------------------------
        # IF ANY ERRORS → STOP
        # --------------------------------------------------

        if errors:
            return None, errors

        # --------------------------------------------------
        # CREATE SIMULATION STATE
        # --------------------------------------------------

        state, message = sim.create_simulation(factory, starting_cash)

        if state is None:
            errors.append("capital")
            return None, errors

        return state, "Simulation created successfully."

    except KeyError as e:
        return None, f"Missing required setup field: {e}"
