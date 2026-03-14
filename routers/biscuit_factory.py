# ============================================================
# BISCUIT FACTORY SIMULATOR ROUTES
# ============================================================

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import json
import uuid

from auth import create_access_token, get_current_user
from templates_config import templates
from database import (
    get_connection,
    get_db,
    delete_team,
    build_team_financials,
    get_active_session,
    create_new_session,
    get_active_session_for_teacher,
    get_session_by_join_code,
    get_session_for_team,
    save_team_simulation_state,
)
from scenario_engine import DEFAULT_SCENARIO
from Simulation_manager import SimulationManager
from decision_engine import create_simulation_from_initial_decisions
import simulation_engine as sim

router = APIRouter()


# ============================================================
# TEAM ENTRY (legacy /app route kept for bookmarks)
# ============================================================

@router.get("/app")
def simulator_entry():
    return RedirectResponse("/student", status_code=303)


# ============================================================
# CREATE SESSION
# ============================================================

@router.post("/create-session")
def create_session(
    request: Request,
    session_name: str = Form(...),
    total_months: int = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)
    create_new_session(session_name, total_months, teacher_id=user["team_id"])
    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# TEAM REGISTRATION
# ============================================================

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, code: str = None):
    return templates.TemplateResponse(
        "biscuit_factory/register.html",
        {"request": request, "prefilled_code": code.upper() if code else None}
    )


@router.post("/register")
def register_team(
    request: Request,
    team_name: str = Form(...),
    password: str = Form(...),
    join_code: str = Form(...)
):
    active_session = get_session_by_join_code(join_code)

    if not active_session:
        return templates.TemplateResponse(
            "biscuit_factory/register.html",
            {"request": request, "error": "Join code not recognised. Check with your teacher."}
        )
    if active_session[2] != "setup":
        return templates.TemplateResponse(
            "biscuit_factory/register.html",
            {"request": request, "error": "Registration is closed. The simulation has already started."}
        )

    session_id = active_session[0]
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM teams WHERE team_name = ?", (team_name,))
        if cursor.fetchone():
            return templates.TemplateResponse(
                "biscuit_factory/register.html",
                {"request": request, "error": "Team name already exists."}
            )

        team_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO teams (team_id, team_name, password, role, simulation, meta, current_month, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (team_id, team_name, password, "team", json.dumps({}), json.dumps({}), 0, session_id))

    token = create_access_token({"team_id": team_id, "team_name": team_name, "role": "team"})
    response = RedirectResponse("/team-dashboard", status_code=303)
    response.set_cookie("access_token", token, httponly=True)
    return response


# ============================================================
# TEACHER DASHBOARD
# ============================================================

@router.get("/teacher-dashboard", response_class=HTMLResponse)
def teacher_dashboard(
    request: Request,
    missing: str = None,
    user=Depends(get_current_user)
):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    active_session = get_active_session_for_teacher(user["team_id"])

    competitive_mode = False
    if active_session:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT competitive_mode FROM simulation_sessions WHERE session_id = ?",
                (active_session[0],)
            )
            result = cursor.fetchone()
            if result and result[0]:
                competitive_mode = True

    scenario_state = {}
    current_month = 0
    total_months = 0
    full_scenarios = {}

    if active_session:
        session_id = active_session[0]
        current_month = active_session[3]
        total_months = active_session[4]

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT scenario_state FROM simulation_sessions WHERE session_id = ?",
                (session_id,)
            )
            result = cursor.fetchone()
        if result and result[0]:
            scenario_state = json.loads(result[0])

        for month in range(1, total_months + 1):
            scenario = DEFAULT_SCENARIO.copy()
            override = scenario_state.get(str(month))
            if override:
                scenario.update(override)
            full_scenarios[str(month)] = scenario

    teams = []
    team_financials = []
    team_count = 0
    missing_teams = []
    popup_missing_teams = []
    submitted_teams = []
    monthly_results = {}

    if missing:
        missing_teams = missing.split(",")

    raw_teams = []
    if active_session:
        session_id = active_session[0]
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT team_id, team_name, password, meta
                FROM teams
                WHERE role = 'team' AND session_id = ?
            """, (session_id,))
            raw_teams = cursor.fetchall()

    if active_session and active_session[2] == "active" and current_month > 1:
        for team_id, team_name, password, meta_blob in raw_teams:
            meta = json.loads(meta_blob) if meta_blob else {}
            if meta.get("decision_month") != current_month:
                popup_missing_teams.append(team_name)

    for team_id, team_name, password, meta_blob in raw_teams:
        meta = json.loads(meta_blob) if meta_blob else {}

        if active_session[2] == "setup":
            if meta.get("setup_complete"):
                submitted_teams.append(team_name)
        else:
            if meta.get("submitted") and meta.get("decision_month") == current_month:
                submitted_teams.append(team_name)

        auto_built = meta.get("auto_built", False)
        teams.append((team_id, team_name, password, auto_built))

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT simulation FROM teams WHERE team_id = ?", (team_id,))
            result = cursor.fetchone()
        if result and result[0]:
            simulation = json.loads(result[0])
            if simulation.get("production_plan"):
                simulation["production_plan"] = {
                    int(k): v for k, v in simulation["production_plan"].items()
                }

        team_count = len(teams)
        team_financials = build_team_financials(session_id)

        monthly_results.clear()
        for month in range(1, total_months + 1):
            monthly_results[month] = []

        for team_id, team_name, password, meta_blob in raw_teams:
            meta = json.loads(meta_blob) if meta_blob else {}
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT simulation FROM teams WHERE team_id = ?", (team_id,))
                result = cursor.fetchone()
            if result and result[0]:
                simulation = json.loads(result[0])
                for report in simulation.get("history", []):
                    month = report["month"]
                    monthly_results[month].append({
                        "team": team_name,
                        "auto_built": meta.get("auto_built", False),
                        "auto_submitted": month in meta.get("auto_submitted_months", []),
                        "quality_system": report.get("quality_system", ""),
                        "units_produced": report["units_produced"],
                        "units_sold": report["units_sold"],
                        "revenue": report["revenue"],
                        "total_cost": report["total_cost"],
                        "profit": report["profit"]
                    })

    join_code = active_session[5] if active_session else None

    return templates.TemplateResponse(
        "biscuit_factory/teacher_dashboard.html",
        {
            "request": request,
            "teams": teams,
            "team_count": team_count,
            "user": user,
            "active_session": active_session,
            "join_code": join_code,
            "missing_teams": missing_teams,
            "popup_missing_teams": popup_missing_teams,
            "submitted_teams": submitted_teams,
            "submitted_count": len(submitted_teams),
            "total_teams": len(teams),
            "team_financials": team_financials,
            "scenarios": full_scenarios,
            "current_month": current_month,
            "total_months": total_months,
            "monthly_results": monthly_results,
            "competitive_mode": competitive_mode,
        }
    )


@router.post("/delete-team/{team_id}")
def delete_team_route(team_id: str, user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)
    delete_team(team_id)
    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# TEAM DASHBOARD
# ============================================================

@router.get("/team-dashboard", response_class=HTMLResponse)
def team_dashboard(request: Request, user=Depends(get_current_user)):
    if not user or user["role"] != "team":
        return RedirectResponse("/app", status_code=303)

    import ingredients_engine as ie
    import production_process as pp
    import factory_engine as fe
    from factory_engine import calculate_utilities_cost

    active_session = get_session_for_team(user["team_id"])

    competitive_mode = False
    team_financials = []

    if active_session:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT competitive_mode FROM simulation_sessions WHERE session_id = ?",
                (active_session[0],)
            )
            result = cursor.fetchone()
            if result and result[0]:
                competitive_mode = True
        team_financials = build_team_financials(active_session[0])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT team_name, simulation, meta FROM teams WHERE team_id = ?",
            (user["team_id"],)
        )
        team = cursor.fetchone()

    simulation = None
    meta = {}
    team_name = ""

    if team:
        team_name, sim_blob, meta_blob = team
        simulation = json.loads(sim_blob) if sim_blob and sim_blob.strip() else None
        meta = json.loads(meta_blob) if meta_blob else {}

        if simulation:
            if simulation.get("history"):
                for month in simulation["history"]:
                    if "cost_breakdown" in month:
                        month["cost_breakdown"].setdefault("monthly_utilities", 0)
            if "starting_cash" not in simulation:
                simulation["starting_cash"] = simulation.get("investment_outstanding", 0)
            if simulation.get("production_plan"):
                simulation["production_plan"] = {
                    int(k): v for k, v in simulation["production_plan"].items()
                }

    biscuit_list = ie.get_all_biscuit_names()

    process_limits = []
    utilities_cost = 0

    if simulation and simulation.get("factory"):
        factory = simulation["factory"]
        if "factory_cost_breakdown" not in simulation:
            simulation["factory_cost_breakdown"] = {
                "wall_cost": fe.calculate_wall_cost(factory),
                "floor_cost": fe.calculate_floor_cost(factory),
                "roof_cost": fe.calculate_roof_cost(factory),
                "fixtures_cost": fe.calculate_fixture_cost(factory),
                "utilities_cost": fe.calculate_utilities_cost(factory)
            }
        utilities_cost = calculate_utilities_cost(factory)
        for line in factory.get("lines", []):
            process_limits.append(pp.get_process_limits(line["process_type"]))

    return templates.TemplateResponse(
        "biscuit_factory/team_dashboard.html",
        {
            "request": request,
            "team_name": team_name,
            "user": user,
            "active_session": active_session,
            "simulation": simulation,
            "meta": meta,
            "biscuit_list": biscuit_list,
            "process_limits": process_limits,
            "competitive_mode": competitive_mode,
            "current_team_id": user["team_id"],
            "team_financials": team_financials,
            "utilities_cost": utilities_cost,
        }
    )


# ============================================================
# SETUP PHASE
# ============================================================

@router.post("/end-setup-phase")
def end_setup_phase(user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    import decision_engine as de

    active_session = get_active_session_for_teacher(user["team_id"])
    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT team_id, meta FROM teams WHERE role = 'team' AND session_id = ?",
            (session_id,)
        )
        teams = cursor.fetchall()
        manager = SimulationManager()

        for team_id, meta_blob in teams:
            meta = json.loads(meta_blob) if meta_blob else {}
            if not meta.get("setup_complete"):
                state, message = de.create_simulation_from_initial_decisions(manager.default_setup)
                if state is None:
                    meta["setup_complete"] = True
                    meta["auto_built"] = True
                    meta["submitted"] = True
                else:
                    cursor.execute(
                        "UPDATE teams SET simulation = ? WHERE team_id = ?",
                        (json.dumps(state), team_id)
                    )
                    meta["setup_complete"] = True
                    meta["auto_built"] = True
                    meta["submitted"] = True
            else:
                meta["auto_built"] = False
                meta["submitted"] = True
            cursor.execute(
                "UPDATE teams SET meta = ? WHERE team_id = ?",
                (json.dumps(meta), team_id)
            )

        cursor.execute("""
            UPDATE simulation_sessions SET status = 'active', current_month = 1
            WHERE session_id = ?
        """, (session_id,))
    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# SUBMIT DECISIONS
# ============================================================

@router.post("/submit-decisions")
async def submit_decisions(request: Request, user=Depends(get_current_user)):
    if not user or user["role"] != "team":
        return RedirectResponse("/app", status_code=303)

    from decision_engine import apply_student_decisions
    import ingredients_engine as ie
    import production_process as pp

    active_session = get_session_for_team(user["team_id"])
    if not active_session:
        return RedirectResponse("/team-dashboard", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT simulation, meta FROM teams WHERE team_id = ?",
            (user["team_id"],)
        )
        result = cursor.fetchone()

    if not result:
        return RedirectResponse("/team-dashboard", status_code=303)

    state = json.loads(result[0])
    meta = json.loads(result[1]) if result[1] else {}
    form = await request.form()

    quality_system = form.get("quality_system")
    production_plan = {}
    line_index = 0
    while True:
        if f"line_{line_index}_exists" not in form:
            break
        runs = []
        run_index = 0
        while True:
            biscuit_key = f"line_{line_index}_biscuit_{run_index}"
            if biscuit_key not in form:
                break
            biscuit = form.get(biscuit_key)
            units = form.get(f"line_{line_index}_units_{run_index}")
            if biscuit and units:
                try:
                    units = float(units)
                    if units > 0:
                        runs.append({"biscuit": biscuit, "units": units})
                except:
                    pass
            run_index += 1
        production_plan[int(line_index)] = runs
        line_index += 1

    decisions = {"quality_system": quality_system, "production_plan": production_plan}
    success, message = apply_student_decisions(state, decisions)

    if not success:
        biscuit_list = ie.get_all_biscuit_names()
        process_limits = []
        for line in state.get("factory", {}).get("lines", []):
            process_limits.append(pp.get_process_limits(line["process_type"]))
        return templates.TemplateResponse(
            "biscuit_factory/team_dashboard.html",
            {
                "request": request,
                "user": user,
                "team_name": "",
                "active_session": active_session,
                "simulation": state,
                "meta": meta,
                "biscuit_list": biscuit_list,
                "process_limits": process_limits,
                "decision_errors": [message],
                "form_production_plan": production_plan,
            }
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE teams SET simulation = ? WHERE team_id = ?",
            (json.dumps(state), user["team_id"])
        )
        meta["submitted"] = True
        meta["decision_month"] = state["month"]
        cursor.execute(
            "UPDATE teams SET meta = ? WHERE team_id = ?",
            (json.dumps(meta), user["team_id"])
        )
    return RedirectResponse("/team-dashboard", status_code=303)


# ============================================================
# RUN MONTH HELPER
# ============================================================

def run_current_month_for_all_teams(session_id, current_month, scenario):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT team_id, team_name, meta FROM teams WHERE role = 'team' AND session_id = ?",
            (session_id,)
        )
        teams = cursor.fetchall()
        updated_meta = {}

        for team_id, team_name, meta_blob in teams:
            meta = json.loads(meta_blob) if meta_blob else {}
            cursor.execute("SELECT simulation FROM teams WHERE team_id = ?", (team_id,))
            sim_blob = cursor.fetchone()[0]
            if not sim_blob:
                continue
            state = json.loads(sim_blob)
            if current_month > 1 and not meta.get("submitted"):
                if "auto_submitted_months" not in meta:
                    meta["auto_submitted_months"] = []
                meta["auto_submitted_months"].append(current_month)
            success, result = sim.run_month(state, scenario)
            if not success:
                print(f"Simulation error for {team_name}: {result}")
                continue
            cursor.execute(
                "UPDATE teams SET simulation = ? WHERE team_id = ?",
                (json.dumps(state), team_id)
            )
            updated_meta[team_id] = meta

        for team_id, meta in updated_meta.items():
            meta["submitted"] = False
            meta["decision_month"] = None
            cursor.execute(
                "UPDATE teams SET meta = ? WHERE team_id = ?",
                (json.dumps(meta), team_id)
            )


# ============================================================
# ADVANCE MONTH
# ============================================================

@router.post("/advance-month")
def advance_month_route(user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    active_session = get_active_session_for_teacher(user["team_id"])
    if not active_session or active_session[2] != "active":
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]
    current_month = active_session[3]
    total_months = active_session[4]
    final_month = current_month == total_months
    next_month = current_month + 1

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scenario_state FROM simulation_sessions WHERE session_id = ?",
            (session_id,)
        )
        scenario_blob = cursor.fetchone()[0]
        scenario_state = json.loads(scenario_blob) if scenario_blob else {}
        scenario = scenario_state.get(str(current_month), DEFAULT_SCENARIO)

        cursor.execute(
            "SELECT team_id, team_name, password, meta FROM teams WHERE role = 'team' AND session_id = ?",
            (session_id,)
        )
        teams = cursor.fetchall()

    missing_teams = []
    for team_id, team_name, password, meta_blob in teams:
        meta = json.loads(meta_blob) if meta_blob else {}
        if meta.get("decision_month") != current_month:
            missing_teams.append(team_name)

    if current_month == 1 and missing_teams:
        return RedirectResponse(
            f"/teacher-dashboard?missing={','.join(missing_teams)}",
            status_code=303
        )

    run_current_month_for_all_teams(session_id, current_month, scenario)

    with get_db() as conn:
        cursor = conn.cursor()
        if final_month:
            cursor.execute(
                "UPDATE simulation_sessions SET status = 'finished' WHERE session_id = ?",
                (session_id,)
            )
        else:
            cursor.execute(
                "UPDATE simulation_sessions SET current_month = ? WHERE session_id = ?",
                (next_month, session_id)
            )
    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# FACTORY SETUP
# ============================================================

@router.get("/factory-setup", response_class=HTMLResponse)
def factory_setup_page(request: Request, user=Depends(get_current_user)):
    if not user or user["role"] != "team":
        return RedirectResponse("/app", status_code=303)

    active_session = get_session_for_team(user["team_id"])
    if not active_session or active_session[2] != "setup":
        return RedirectResponse("/team-dashboard", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT team_name, meta FROM teams WHERE team_id = ?",
            (user["team_id"],)
        )
        result = cursor.fetchone()

    if not result:
        return RedirectResponse("/team-dashboard", status_code=303)

    team_name, meta_blob = result
    meta = json.loads(meta_blob) if meta_blob else {}
    if meta.get("setup_complete"):
        return RedirectResponse("/team-dashboard", status_code=303)

    return templates.TemplateResponse(
        "biscuit_factory/factory_setup.html",
        {"request": request, "team_name": team_name, "user": user}
    )


@router.post("/factory-setup")
def submit_factory_setup(
    request: Request,
    starting_cash: int = Form(...),
    length_m: int = Form(...),
    width_m: int = Form(...),
    wall_small: int = Form(0),
    wall_medium: int = Form(0),
    wall_large: int = Form(0),
    industrial_door: int = Form(0),
    pedestrian_door: int = Form(0),
    window: int = Form(0),
    floor_slabs: int = Form(0),
    roof_panels: int = Form(0),
    job: int = Form(0),
    batch: int = Form(0),
    cell: int = Form(0),
    flow: int = Form(0),
    quality_system: str = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["role"] != "team":
        return RedirectResponse("/app", status_code=303)

    import decision_engine as de

    team_id = user["team_id"]

    production_lines = (["job"] * job + ["batch"] * batch +
                        ["cell"] * cell + ["flow"] * flow)

    setup_data = {
        "starting_cash": starting_cash,
        "factory": {
            "length_m": length_m, "width_m": width_m,
            "wall_blocks": {"small": wall_small, "medium": wall_medium, "large": wall_large},
            "fixtures": {"industrial_door": industrial_door, "pedestrian_door": pedestrian_door, "window": window},
            "floor_slabs": floor_slabs, "roof_panels": roof_panels,
            "production_lines": production_lines,
            "quality_system": quality_system
        }
    }

    state, message = de.create_simulation_from_initial_decisions(setup_data)

    if state is None:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT team_name FROM teams WHERE team_id = ?", (team_id,))
            team_name = cursor.fetchone()[0]
        mapping = {
            "floor_slabs": "Floor slabs — not enough",
            "roof_panels": "Roof panels — not enough",
            "wall_blocks": "Wall blocks — not enough",
            "capital": "Investment requested — not enough",
            "space": "Factory space — not enough space for staff/goods movements and welfare facilities",
            "doors": "Doors — not enough",
            "lines": "Production lines — not enough",
            "quality": "Quality system — not selected"
        }
        friendly_messages = []
        if isinstance(message, list):
            for error in message:
                friendly_messages.append(mapping.get(error, str(error)))
        else:
            friendly_messages.append(str(message))
        return templates.TemplateResponse(
            "biscuit_factory/factory_setup.html",
            {"request": request, "team_name": team_name, "user": user,
             "errors": friendly_messages, "form_data": setup_data}
        )

    active_session = get_session_for_team(user["team_id"])
    state["max_months"] = active_session[4]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE teams SET simulation = ? WHERE team_id = ?",
            (json.dumps(state), team_id)
        )
        cursor.execute("SELECT meta FROM teams WHERE team_id = ?", (team_id,))
        meta_blob = cursor.fetchone()[0]
        meta = json.loads(meta_blob) if meta_blob else {}
        meta["submitted"] = True
        meta["setup_complete"] = True
        meta["auto_built"] = False
        cursor.execute(
            "UPDATE teams SET meta = ? WHERE team_id = ?",
            (json.dumps(meta), team_id)
        )
    return RedirectResponse("/team-dashboard", status_code=303)


# ============================================================
# TEACHER ACTIONS
# ============================================================

@router.post("/rename-team")
def rename_team(
    team_id: str = Form(...),
    new_name: str = Form(...),
    user=Depends(get_current_user)
):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE teams SET team_name = ? WHERE team_id = ?", (new_name, team_id))
    return RedirectResponse("/teacher-dashboard", status_code=303)


@router.post("/update-scenario")
def update_scenario(
    request: Request,
    month: int = Form(...),
    name: str = Form(...),
    scrap_qc: float = Form(...),
    scrap_qa: float = Form(...),
    scrap_tqm: float = Form(...),
    ingredient_multiplier: float = Form(...),
    shipping_multiplier: float = Form(...),
    sales_price_multiplier: float = Form(...),
    demand_multiplier: float = Form(...),
    extra_fixed_cost: float = Form(...),
    machine_breakdown: float = Form(0),
    employee_strike: float = Form(0),
    user=Depends(get_current_user)
):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    active_session = get_active_session_for_teacher(user["team_id"])
    session_id = active_session[0]
    current_month = active_session[3]

    if month < current_month:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scenario_state FROM simulation_sessions WHERE session_id = ?",
            (session_id,)
        )
        result = cursor.fetchone()
        scenario_state = json.loads(result[0]) if result and result[0] else {}
        scenario_state[str(month)] = {
            "name": name,
            "scrap_rate": {"qc": scrap_qc, "qa": scrap_qa, "tqm": scrap_tqm},
            "machine_breakdown": machine_breakdown,
            "employee_strike": employee_strike,
            "ingredient_multiplier": ingredient_multiplier,
            "shipping_multiplier": shipping_multiplier,
            "sales_price_multiplier": sales_price_multiplier,
            "demand_multiplier": demand_multiplier,
            "extra_fixed_cost": extra_fixed_cost
        }
        cursor.execute(
            "UPDATE simulation_sessions SET scenario_state = ? WHERE session_id = ?",
            (json.dumps(scenario_state), session_id)
        )
    return RedirectResponse("/teacher-dashboard", status_code=303)


@router.post("/end-session")
def end_session(user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    active_session = get_active_session_for_teacher(user["team_id"])
    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]
    current_month = active_session[3]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scenario_state FROM simulation_sessions WHERE session_id = ?",
            (session_id,)
        )
        result = cursor.fetchone()
        scenario_state = json.loads(result[0]) if result and result[0] else {}
        scenario = scenario_state.get(str(current_month), DEFAULT_SCENARIO)

    run_current_month_for_all_teams(session_id, current_month, scenario)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE simulation_sessions SET status = 'finished', current_month = ?
            WHERE session_id = ?
        """, (current_month, session_id))
    return RedirectResponse("/teacher-dashboard", status_code=303)


@router.post("/delete-session")
def delete_session(user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    active_session = get_active_session_for_teacher(user["team_id"])
    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM teams WHERE session_id = ? AND role = 'team'",
            (session_id,)
        )
        cursor.execute("DELETE FROM simulation_sessions WHERE session_id = ?", (session_id,))
    return RedirectResponse("/teacher-dashboard", status_code=303)


@router.post("/make-competitive")
def make_competitive(user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    active_session = get_active_session_for_teacher(user["team_id"])
    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE simulation_sessions SET competitive_mode = 1 WHERE session_id = ?",
            (active_session[0],)
        )
    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# CREATE PDF REPORTS
# ============================================================

@router.post("/create-pdfs")
def create_pdfs(user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return {"error": "Unauthorised"}

    session = get_active_session_for_teacher(user["team_id"])
    if not session:
        return {"error": "No active session found"}

    from pdf_engine import generate_all_reports, create_zip
    files = generate_all_reports(session[0])
    zip_path = create_zip(files)
    return FileResponse(zip_path, media_type="application/zip", filename="simulation_reports.zip")
