# ==========================================================
# SIMULATION ENGINE
# ----------------------------------------------------------
# This is the core financial engine of the Biscuit Factory
# Simulator.
#
# This file is responsible for:
# - Creating the simulation state
# - Running monthly operational calculations
# - Applying scenario effects
# - Applying quality system switching costs
# - Updating financial results
#
# IMPORTANT DESIGN RULE:
# This engine assumes all student decisions are already
# validated. Validation is handled by decision_engine.
#
# This file does NOT:
# - Validate student inputs
# - Modify factory structure
#
# It only performs financial and operational calculations.
# ==========================================================

import factory_engine as fe
import production_process as pp
import ingredients_engine as ie
import quality_engine as qe
import scenario_engine as se


# ==========================================================
# CREATE SIMULATION STATE
# ==========================================================

def create_simulation(factory, starting_cash):

    # --------------------------------------------------
    # FACTORY COST BREAKDOWN
    # --------------------------------------------------

    factory_cost_breakdown = {
        "wall_cost": fe.calculate_wall_cost(factory),
        "floor_cost": fe.calculate_floor_cost(factory),
        "roof_cost": fe.calculate_roof_cost(factory),
        "fixtures_cost": fe.calculate_fixture_cost(factory),
        "utilities_cost": fe.calculate_utilities_cost(factory)
    }

    build_cost = sum(factory_cost_breakdown.values())

    if build_cost is None:
        return None, "Factory build incomplete. Walls not finished."

    # Calculate capital investment in production machinery
    machinery_cost = sum(
        pp.calculate_capital_cost(line["process_type"])
        for line in factory["lines"]
    )

    # Initial quality system setup cost (if selected at setup stage)
    quality_setup_cost = 0
    if factory.get("quality_system"):
        quality_setup_cost = qe.get_initial_quality_cost(factory["quality_system"])

    total_initial_investment = (
        build_cost +
        machinery_cost +
        quality_setup_cost
    )

    # Check if starting cash is sufficient
    if total_initial_investment > starting_cash:
        return None, (
            f"Insufficient investment. Required £{total_initial_investment:,.2f}, "
            f"but only £{starting_cash:,.2f} available."
        )

    unused_capital = starting_cash - total_initial_investment

    # Central simulation state dictionary
    state = {
        "factory": factory,
        "initial_quality_system": factory.get("quality_system"),
        "month": 1,
        "cash": 0,
        "build_cost": build_cost,
        "factory_cost_breakdown": factory_cost_breakdown,
        "machinery_cost": machinery_cost,
        "quality_setup_cost": quality_setup_cost,
        "total_initial_investment": total_initial_investment,
        "investment_outstanding": starting_cash,
        "unused_capital": unused_capital,
        "production_plan": {},
        "history": [],
        "phase": "setup",
        "current_quality_system": None,  # Tracks switching between months
        "cumulative_profit": 0,
        "starting_cash": starting_cash,
    }

    return state, "Simulation created successfully."


# ==========================================================
# MONTHLY OPERATIONS CALCULATION
# ==========================================================

def calculate_month_operations(state, production_plan, scenario, quality_change_cost=0):

    # Performs all operational calculations for a single month
    # Returns structured financial results

    factory = state["factory"]

    total_units_produced = 0
    total_revenue = 0

    # Track production per biscuit type
    biscuit_production = {}

    # Full cost breakdown dictionary
    cost_breakdown = {
        "ingredients": 0,
        "labour": 0,
        "changeover": 0,
        "monthly_utilities": 0,
        "shipping": 0,
        "quality_system": 0,
        "machine_breakdown": 0,
        "employee_strike": 0,
        "extra_fixed_cost": 0,
        "quality_system_change_cost": 0
    }

    # --------------------------------------------------
    # PRODUCTION LOOP (Per Line)
    # --------------------------------------------------

    for line_index, runs in production_plan.items():
        line_index = int(line_index)

        line = factory["lines"][line_index]
        process_type = line["process_type"]

        # -----------------------------
        # CHANGEOVER COST
        # -----------------------------
        # Charged when more than one run is performed on a line
        if len(runs) > 1:
            number_of_changeovers = len(runs) - 1
            changeover_cost_per = pp.calculate_changeover_cost(process_type)
            total_changeover_cost = number_of_changeovers * changeover_cost_per
            cost_breakdown["changeover"] += total_changeover_cost

        # -----------------------------
        # LABOUR COST
        # -----------------------------
        labour_cost = pp.calculate_labour_cost(process_type)
        cost_breakdown["labour"] += labour_cost

        # -----------------------------
        # UTILITIES COST
        # -----------------------------
        monthly_utilities_cost = pp.calculate_monthly_utilities_cost(process_type)
        cost_breakdown["monthly_utilities"] += monthly_utilities_cost

        # -----------------------------
        # EMPLOYEE STRIKE COST
        # -----------------------------
        strike_cost_per_10_percent = scenario.get("employee_strike", 0)

        if strike_cost_per_10_percent > 0:
            labour_intensity = pp.get_labour_intensity(process_type)
            intensity_blocks = labour_intensity / 10
            strike_cost = intensity_blocks * strike_cost_per_10_percent
            cost_breakdown["employee_strike"] += strike_cost

        # -----------------------------
        # RUN LOOP (Per Biscuit)
        # -----------------------------
        for run in runs:
            biscuit = run["biscuit"]
            units = run["units"]

            # Ingredient cost with scenario multiplier
            ingredient_cost_per_unit = ie.calculate_ingredient_cost(biscuit)
            ingredient_multiplier = scenario.get("ingredient_multiplier", 1)
            adjusted_cost = ingredient_cost_per_unit * ingredient_multiplier
            ingredient_cost = adjusted_cost * units

            total_units_produced += units

            if biscuit not in biscuit_production:
                biscuit_production[biscuit] = 0

            biscuit_production[biscuit] += units
            cost_breakdown["ingredients"] += ingredient_cost

    # --------------------------------------------------
    # DEMAND, SCRAP, REVENUE CALCULATION
    # --------------------------------------------------

    total_units_sold = 0

    for biscuit, produced_units in biscuit_production.items():

        # -----------------------------
        # APPLY SCRAP RATE
        # -----------------------------
        scrap_rates = scenario.get("scrap_rate")

        if scrap_rates and factory.get("quality_system") in scrap_rates:
            scrap_rate = scrap_rates[factory["quality_system"]]
        else:
            scrap_rate = 0

        saleable_units = produced_units * (1 - scrap_rate)

        # -----------------------------
        # APPLY DEMAND LIMIT
        # -----------------------------
        base_demand = ie.get_monthly_demand(biscuit)
        demand_multiplier = scenario.get("demand_multiplier", 1)
        max_demand = base_demand * demand_multiplier

        units_sold = min(saleable_units, max_demand)

        # -----------------------------
        # APPLY PRICE MULTIPLIER
        # -----------------------------
        selling_price = ie.get_batch_price(biscuit)
        price_multiplier = scenario.get("sales_price_multiplier", 1)
        adjusted_price = selling_price * price_multiplier

        revenue = adjusted_price * units_sold

        total_units_sold += units_sold
        total_revenue += revenue

    # --------------------------------------------------
    # EXTRA FIXED COST
    # --------------------------------------------------

    cost_breakdown["extra_fixed_cost"] += scenario.get("extra_fixed_cost", 0)

    # --------------------------------------------------
    # MACHINE BREAKDOWN COST
    # --------------------------------------------------

    breakdown_cost_per_10000 = scenario.get("machine_breakdown", 0)

    if breakdown_cost_per_10000 > 0:
        breakdown_blocks = total_units_produced / 10000
        machine_breakdown_cost = breakdown_blocks * breakdown_cost_per_10000
        cost_breakdown["machine_breakdown"] += machine_breakdown_cost

    # --------------------------------------------------
    # SHIPPING COST
    # --------------------------------------------------

    if total_units_sold > 0:
        base_shipping_cost = pp.calculate_shipping_cost(total_units_sold)
        shipping_multiplier = scenario.get("shipping_multiplier", 1)
        adjusted_shipping_cost = base_shipping_cost * shipping_multiplier
        cost_breakdown["shipping"] += adjusted_shipping_cost

    # --------------------------------------------------
    # QUALITY SYSTEM MONTHLY COST
    # --------------------------------------------------

    quality_system = factory.get("quality_system")

    if quality_system:
        monthly_quality_cost = qe.get_monthly_quality_cost(quality_system)
        cost_breakdown["quality_system"] += monthly_quality_cost

    # --------------------------------------------------
    # QUALITY SYSTEM CHANGE COST
    # --------------------------------------------------

    if quality_change_cost > 0:
        cost_breakdown["quality_system_change_cost"] += quality_change_cost

    # --------------------------------------------------
    # TOTAL COST AND PROFIT
    # --------------------------------------------------

    total_cost = sum(cost_breakdown.values())
    profit = total_revenue - total_cost

    return {
        "units_produced": total_units_produced,
        "units_sold": total_units_sold,
        "revenue": total_revenue,
        "cost_breakdown": cost_breakdown,
        "total_cost": total_cost,
        "profit": profit
    }


# ==========================================================
# RUN ONE MONTH
# ==========================================================

def run_month(state,scenario):

    production_plan = state.get("production_plan")

    if not production_plan:
        return False, "No production plan submitted."


    # --------------------------------------------------
    # QUALITY SYSTEM SWITCH LOGIC
    # --------------------------------------------------

    new_quality_system = state["factory"].get("quality_system")
    previous_quality_system = state.get("current_quality_system")
    initial_quality_system = state.get("initial_quality_system")

    quality_change_cost = 0

    # --------------------------------------------------
    # FIRST MONTH LOGIC
    # --------------------------------------------------
    if state["month"] == 1:

        # If student changed the system during Month 1 decisions
        if new_quality_system != initial_quality_system and new_quality_system:

            quality_change_cost = qe.get_initial_quality_cost(new_quality_system)

        state["current_quality_system"] = new_quality_system

    # --------------------------------------------------
    # MONTH 2+ LOGIC
    # --------------------------------------------------
    else:

        if new_quality_system != previous_quality_system and new_quality_system:

            quality_change_cost = qe.get_initial_quality_cost(new_quality_system)

        state["current_quality_system"] = new_quality_system

    # --------------------------------------------------
    # CALCULATE OPERATIONS
    # --------------------------------------------------

    try:
        results = calculate_month_operations(
            state,
            production_plan,
            scenario,
            quality_change_cost
        )
    except Exception as e:
        return False, f"Simulation error: {str(e)}"

    # --------------------------------------------------
    # UPDATE FINANCIAL STATE (Overdraft-First Model)
    # --------------------------------------------------

    profit = results["profit"]

    # ----------------------------------------
    # Update cumulative profit
    # ----------------------------------------
    state["cumulative_profit"] += profit

    # ----------------------------------------
    # Apply profit / loss
    # ----------------------------------------

    # 1️⃣ LOSS → immediately reduces cash (can go negative)
    if profit < 0:
        state["cash"] += profit


    # 2️⃣ PROFIT → allocate in order:
    else:
        remaining_profit = profit

        # Step A — Repair overdraft first
        if state["cash"] < 0:
            repair_amount = min(
                remaining_profit,
                abs(state["cash"])
            )
            state["cash"] += repair_amount
            remaining_profit -= repair_amount

        # Step B — Repay loan if still outstanding
        if remaining_profit > 0 and state["investment_outstanding"] > 0:
            repayment = min(
                remaining_profit,
                state["investment_outstanding"]
            )
            state["investment_outstanding"] -= repayment
            remaining_profit -= repayment

        # Step C — If loan cleared, remaining profit builds cash
        if remaining_profit > 0:
            state["cash"] += remaining_profit

    report = {
        "month": state["month"],
        "scenario": scenario["name"],
        "quality_system": state["factory"].get("quality_system", ""),
        "units_produced": results["units_produced"],
        "units_sold": results["units_sold"],
        "revenue": results["revenue"],

        "cost_breakdown": results["cost_breakdown"],
        "total_cost": results["total_cost"],
        "profit": results["profit"],

        "cumulative_profit": state["cumulative_profit"],
        "cash": state["cash"],
        "remaining_investment_to_recover": state["investment_outstanding"],
        "loan_cleared_this_month": state["investment_outstanding"] == 0
    }

    state["history"].append(report)

    state["month"] += 1
    state["phase"] = "operating"

    return True, report
