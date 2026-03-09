# ==========================================================
# SIMULATION MANAGER
# ==========================================================
# Multi-team orchestration layer.
#
# Responsibilities:
# - Manage multiple teams
# - Store submission state
# - Control month advancement
# - Delegate validation to decision_engine
# - Delegate financial logic to simulation_engine
#
# Does NOT:
# - Perform calculations
# - Modify engine logic
# ==========================================================

import simulation_engine as sim
import decision_engine as de


class SimulationManager:

    # --------------------------------------------------
    # INITIALISE MANAGER
    # --------------------------------------------------

    def __init__(self):
        self.simulations = {}   # team_id → simulation state
        self.team_meta = {}     # team_id → metadata
        self.current_month = 1
        self.default_setup = {
            "starting_cash": 300000,
            "factory": {
                "length_m": 18,
                "width_m": 12,
                "wall_blocks": {
                    "small": 2,
                    "medium": 4,
                    "large": 10
                },
                "fixtures": {
                    "industrial_door": 2,
                    "pedestrian_door": 2,
                    "window": 4
                },
                "floor_slabs": 6,
                "roof_panels": 216,

                # 🔥 IMPORTANT — what decision_engine expects
                "production_lines": ["batch", "job"],
                "quality_system": "qc"
            }
        }

    # --------------------------------------------------
    # CREATE NEW TEAM
    # --------------------------------------------------

    def create_team(self, team_id, max_months):

        if team_id in self.team_meta:
            return False, "Team already exists."

        # No simulation built yet
        self.simulations[team_id] = None

        self.team_meta[team_id] = {
            "phase": "setup",
            "setup_submitted": False,
            "submitted": False,
            "pending_decisions": None,
            "last_decisions": None,
            "max_months": max_months,
            "auto_built": False
        }

        return True, {"phase": "setup"}

    # --------------------------------------------------
    # CREATE FACTORY
    # --------------------------------------------------

    def submit_setup(self, team_id, setup_decisions):

        if team_id not in self.team_meta:
            return False, "Team not found."

        meta = self.team_meta[team_id]

        if meta["phase"] != "setup":
            return False, "Setup already completed."

        state, message = de.create_simulation_from_initial_decisions(
            setup_decisions
        )

        if state is None:
            return False, message

        state["max_months"] = meta["max_months"]
        state["team_id"] = team_id
        state["phase"] = "operating"

        self.simulations[team_id] = state

        meta["phase"] = "operating"
        meta["setup_submitted"] = True

        return True, "Setup completed successfully"


    # --------------------------------------------------
    # TEAM SUBMITS DECISIONS (NO EXECUTION)
    # --------------------------------------------------

    def submit_decisions(self, team_id, monthly_decisions):

        if self.team_meta[team_id]["phase"] != "operating":
            return False, "Team must complete setup first."

        state = self.simulations.get(team_id)
        meta = self.team_meta.get(team_id)

        if not state:
            return False, "Team not found."

        if meta["submitted"]:
            return False, "Decisions already submitted for this month."

        # Store decisions only (do not run simulation yet)
        meta["pending_decisions"] = monthly_decisions
        meta["submitted"] = True

        return True, "Decisions submitted. Awaiting teacher advance."

    # --------------------------------------------------
    # TEACHER ADVANCES MONTH FOR ALL TEAMS
    # --------------------------------------------------

    def advance_month(self):

        results = {}

        # ----------------------------------
        # Auto-build default factory safely
        # ----------------------------------
        for team_id, meta in self.team_meta.items():

            if meta.get("phase", "operating") == "setup":

                state, message = de.create_simulation_from_initial_decisions(
                    self.default_setup
                )
                state["max_months"] = meta.get("max_months", 6)
                state["team_id"] = team_id
                state["phase"] = "operating"

                self.simulations[team_id] = state

                meta["phase"] = "operating"
                meta["setup_submitted"] = True
                meta["auto_built"] = True

        # ----------------------------------
        # Run month for all operating teams
        # ----------------------------------
        for team_id, state in self.simulations.items():

            meta = self.team_meta.get(team_id, {})

            if meta.get("submitted"):
                decisions = meta.get("pending_decisions")
            else:
                decisions = meta.get("last_decisions")

            if decisions is None:
                continue

            success, message = de.apply_student_decisions(
                state,
                decisions
            )

            if not success:
                results[team_id] = {
                    "success": False,
                    "error": message
                }
                continue

            month_result = sim.run_month(state)

            results[team_id] = {
                "success": True,
                "result": month_result
            }

            meta["last_decisions"] = decisions
            meta["pending_decisions"] = None
            meta["submitted"] = False

        self.current_month += 1

        return True, {
            "message": "Month advanced successfully.",
            "new_month": self.current_month,
            "results": results
        }
    # --------------------------------------------------
    # TEACHER CAN REOPEN A TEAM
    # --------------------------------------------------

    def reopen_team(self, team_id):

        meta = self.team_meta.get(team_id)

        if not meta:
            return False, "Team not found."

        meta["submitted"] = False
        meta["pending_decisions"] = None

        return True, "Team reopened for resubmission."

    # --------------------------------------------------
    # GET CLASS STATUS (TEACHER VIEW)
    # --------------------------------------------------

    def get_class_status(self):

        return {
            "current_month": self.current_month,
            "teams": [
                {
                    "team_id": team_id,
                    "submitted": self.team_meta[team_id]["submitted"]
                }
                for team_id in self.simulations
            ]
        }

    # --------------------------------------------------
    # GET TEAM STATUS (TEAM VIEW)
    # --------------------------------------------------

    def get_team_status(self, team_id):

        meta = self.team_meta.get(team_id)

        if not meta:
            return False, "Team not found."

        return True, {
            "current_month": self.current_month,
            "submitted": meta["submitted"],
            "phase": meta["phase"],
            "auto_built": meta.get("auto_built", False)
        }

    # --------------------------------------------------
    # GET FULL TEAM STATE
    # --------------------------------------------------

    def get_team_state(self, team_id):

        state = self.simulations.get(team_id)

        if not state:
            return False, "Team not found."

        return True, state

    # --------------------------------------------------
    # GET TEAM HISTORY
    # --------------------------------------------------

    def get_team_history(self, team_id):

        state = self.simulations.get(team_id)

        if not state:
            return False, "Team not found."

        return True, state.get("history", [])