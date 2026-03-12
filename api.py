# ============================================================
# 🏭 BISCUIT FACTORY SIMULATOR - MAIN API FILE
# ============================================================

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from datetime import datetime, timedelta
import uuid
from database import save_team_simulation_state
from scenario_engine import DEFAULT_SCENARIO

from Simulation_manager import SimulationManager
from database import (
    get_connection,
    init_db,
    delete_team
)
from database import get_active_session, create_new_session
from decision_engine import create_simulation_from_initial_decisions
import json
import simulation_engine as sim
from pdf_engine import generate_all_reports, create_zip
from fastapi.responses import FileResponse

# ============================================================
# APP SETUP
# ============================================================

app = FastAPI()
init_db()

def ensure_teacher_exists():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM teams WHERE role = 'teacher'")
    teacher = cursor.fetchone()

    if not teacher:
        cursor.execute("""
            INSERT INTO teams (
                team_id,
                team_name,
                password,
                role,
                simulation,
                meta,
                current_month,
                session_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            "teacher",
            "teacher123",
            "teacher",
            json.dumps({}),
            json.dumps({}),
            0,
            None
        ))
        conn.commit()

    conn.close()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

ensure_teacher_exists()

manager = SimulationManager()

SECRET_KEY = "SUPER_SECRET_KEY"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ============================================================
# HOMEPAGE
# ============================================================

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):

    host = request.headers.get("host", "")

    # If the user is on the simulator subdomain
    if host.startswith("sim."):
        return templates.TemplateResponse(
            "home.html",
            {"request": request}
        )

    # Otherwise show the marketing homepage
    return templates.TemplateResponse(
        "marketing/homepage.html",
        {"request": request}
    )

# ============================================================
# AUTH HELPERS
# ============================================================

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "team_id": payload.get("team_id"),
            "role": payload.get("role")
        }
    except JWTError:
        return None


def authenticate_user(team_name: str, password: str):

    conn = get_connection()
    cursor = conn.cursor()

    # ---------------------------------
    # TEACHER LOGIN
    # ---------------------------------
    if team_name == "teacher":
        cursor.execute(
            "SELECT team_id, password FROM teams WHERE role = 'teacher'"
        )
        teacher = cursor.fetchone()
        conn.close()

        if teacher and teacher[1] == password:
            return {
                "team_id": teacher[0],
                "team_name": "teacher",
                "role": "teacher"
            }
        return None

    # ---------------------------------
    # TEAM LOGIN
    # ---------------------------------
    cursor.execute(
        "SELECT team_id, team_name, password, role FROM teams WHERE team_name = ?",
        (team_name,)
    )
    user = cursor.fetchone()
    conn.close()

    if user and user[2] == password:
        return {
            "team_id": user[0],
            "team_name": user[1],
            "role": user[3]
        }

    return None


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "user": user}
    )

# ============================================================
# CREATE SESSION
# ============================================================

@app.post("/create-session")
def create_session(
    request: Request,
    session_name: str = Form(...),
    total_months: int = Form(...),
    user=Depends(get_current_user)
):
    from database import create_new_session

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    create_new_session(session_name, total_months)

    return RedirectResponse("/teacher-dashboard", status_code=303)

# ============================================================
# LOGIN ROUTES
# ============================================================

@app.get("/teacher-login", response_class=HTMLResponse)
def teacher_login_page(request: Request):
    return templates.TemplateResponse(
        "teacher_login.html",
        {"request": request}
    )


@app.post("/teacher-login")
def teacher_login(
    request: Request,
    team_name: str = Form(...),
    password: str = Form(...)
):
    user = authenticate_user(team_name, password)

    if not user or user["role"] != "teacher":
        return templates.TemplateResponse(
            "teacher_login.html",
            {"request": request, "error": "Wrong teacher credentials"}
        )

    token = create_access_token(
        {"team_id": user["team_id"], "role": user["role"]}
    )

    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("access_token", token, httponly=True)
    return response


@app.get("/team-login", response_class=HTMLResponse)
def team_login_page(request: Request):
    return templates.TemplateResponse(
        "team_login.html",
        {"request": request}
    )


@app.post("/team-login")
def team_login(
    request: Request,
    team_name: str = Form(...),
    password: str = Form(...)
):
    user = authenticate_user(team_name, password)

    if not user or user["role"] != "team":
        return templates.TemplateResponse(
            "team_login.html",
            {"request": request, "error": "Wrong team name or password"}
        )

    token = create_access_token(
        {"team_id": user["team_id"], "role": user["role"]}
    )

    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("access_token", token, httponly=True)
    return response

# ============================================================
# REGISTRATION
# ============================================================

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request}
    )


@app.post("/register")
def register_team(
    request: Request,
    team_name: str = Form(...),
    password: str = Form(...)
):
    from database import get_active_session
    import uuid
    import json

    active_session = get_active_session()

    if not active_session:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "No active simulation session. Please wait for your teacher."
            }
        )

    # 🚫 Block late joiners
    if active_session[2] != "setup":   # status column
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Registration is closed. The simulation has already started."
            }
        )

    session_id = active_session[0]  # session_id is first column

    conn = get_connection()
    cursor = conn.cursor()

    # 2️⃣ Prevent duplicate team names
    cursor.execute(
        "SELECT * FROM teams WHERE team_name = ?",
        (team_name,)
    )

    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Team name already exists."
            }
        )

    # 3️⃣ Create team attached to session
    team_id = str(uuid.uuid4())

    cursor.execute("""
        INSERT INTO teams (
            team_id,
            team_name,
            password,
            role,
            simulation,
            meta,
            current_month,
            session_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        team_id,
        team_name,
        password,
        "team",
        json.dumps({}),   # simulation state starts empty
        json.dumps({}),   # meta starts empty
        0,
        session_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)

# ============================================================
# DASHBOARD ROUTER
# ============================================================

@app.get("/dashboard")
def dashboard(user=Depends(get_current_user)):

    if not user:
        return RedirectResponse("/", status_code=303)

    if user["role"] == "teacher":
        return RedirectResponse("/teacher-dashboard", status_code=303)

    return RedirectResponse("/team-dashboard", status_code=303)

# ============================================================
# BUILD TEAM FINANCIAL PERFORMANCE DATA
# ============================================================

def build_team_financials(session_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, team_name
        FROM teams
        WHERE role = 'team' AND session_id = ?
    """, (session_id,))

    teams = cursor.fetchall()

    team_financials = []

    for team_id, team_name in teams:

        cursor.execute(
            "SELECT simulation FROM teams WHERE team_id = ?",
            (team_id,)
        )

        result = cursor.fetchone()

        if result and result[0]:

            simulation = json.loads(result[0])

            history = simulation.get("history", [])

            total_units_produced = 0
            total_units_sold = 0
            total_revenue = 0
            total_ingredient_cost = 0
            total_labour_cost = 0
            total_overheads = 0

            for month in history:

                total_units_produced += month.get("units_produced", 0)
                total_units_sold += month.get("units_sold", 0)
                total_revenue += month.get("revenue", 0)
                cost_breakdown = month.get("cost_breakdown", {})
                total_ingredient_cost += cost_breakdown.get("ingredients", 0)
                total_labour_cost += cost_breakdown.get("labour", 0)
                total_overheads += (
                    cost_breakdown.get("changeover", 0)
                    + cost_breakdown.get("shipping", 0)
                    + cost_breakdown.get("quality_system", 0)
                    + cost_breakdown.get("monthly_utilities", 0)
                    + cost_breakdown.get("machine_breakdown", 0)
                    + cost_breakdown.get("employee_strike", 0)
                    + cost_breakdown.get("extra_fixed_cost", 0)
                    + cost_breakdown.get("quality_system_change_cost", 0)
                )

            margin = 0
            if total_revenue > 0:
                margin = (total_revenue - (total_ingredient_cost + total_labour_cost)) / total_revenue

            team_financials.append({
                "id": team_id,
                "name": team_name,
                "initial_investment": simulation.get("total_initial_investment", 0),
                "unused_capital": simulation.get("unused_capital", 0),
                "remaining_investment": simulation.get("investment_outstanding", 0),
                "cumulative_profit": simulation.get("cumulative_profit", 0),
                "cash": simulation.get("cash", 0),
                "total_units_produced": total_units_produced,
                "total_units_sold": total_units_sold,
                "margin": margin,
                "overheads": total_overheads,
            })

        else:

            team_financials.append({
                "id": team_id,
                "name": team_name,
                "initial_investment": 0,
                "unused_capital": 0,
                "remaining_investment": 0,
                "cumulative_profit": 0,
                "cash": 0,
                "total_units_produced": 0,
                "total_units_sold": 0,
                "margin": 0
            })

    conn.close()

    return team_financials

# ============================================================
# TEACHER DASHBOARD
# ============================================================

@app.get("/teacher-dashboard", response_class=HTMLResponse)
def teacher_dashboard(
    request: Request,
    missing: str = None,
    user=Depends(get_current_user)
):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    conn = get_connection()
    cursor = conn.cursor()

    active_session = get_active_session()

    # --------------------------------------------------
    # Competitive mode check
    # --------------------------------------------------

    competitive_mode = False

    if active_session:

        cursor.execute("""
            SELECT competitive_mode
            FROM simulation_sessions
            WHERE session_id = ?
        """, (active_session[0],))

        result = cursor.fetchone()

        if result and result[0]:
            competitive_mode = True

    scenario_state = {}
    current_month = 0
    total_months = 0

    # ✅ FIX: ensure this always exists
    full_scenarios = {}

    # ✅ FIX: ensure this always exists
    full_scenarios = {}

    if active_session:
        session_id = active_session[0]
        current_month = active_session[3]
        total_months = active_session[4]

        cursor.execute("""
            SELECT scenario_state
            FROM simulation_sessions
            WHERE session_id = ?
        """, (session_id,))

        result = cursor.fetchone()

        if result and result[0]:
            scenario_state = json.loads(result[0])

        # --------------------------------------------------
        # Build full scenario map (merge defaults + overrides)
        # --------------------------------------------------

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

    if active_session:

        session_id = active_session[0]

        # --------------------------------------------------
        # 1️⃣ Fetch all teams FIRST
        # --------------------------------------------------
        cursor.execute("""
            SELECT team_id, team_name, password, meta
            FROM teams
            WHERE role = 'team' AND session_id = ?
        """, (session_id,))

    raw_teams = cursor.fetchall()

    # --------------------------------------------------
    # Calculate missing teams ONLY for popup (months >1)
    # --------------------------------------------------

    if active_session and active_session[2] == "active" and current_month > 1:

        for team_id, team_name, password, meta_blob in raw_teams:

            meta = json.loads(meta_blob) if meta_blob else {}

            if meta.get("decision_month") != current_month:
                popup_missing_teams.append(team_name)

# --------------------------------------------------
# 2️⃣ Process teams list
# --------------------------------------------------
    for team_id, team_name, password, meta_blob in raw_teams:

        meta = json.loads(meta_blob) if meta_blob else {}

        # Setup phase submission check
        if active_session[2] == "setup":
            if meta.get("setup_complete"):
                submitted_teams.append(team_name)

        # Operating phase submission check
        else:
            if meta.get("submitted") and meta.get("decision_month") == current_month:
                submitted_teams.append(team_name)

        auto_built = meta.get("auto_built", False)
        teams.append((team_id, team_name, password, auto_built))

        # --------------------------------------------------
        # 3️⃣ Build financial summary
        # --------------------------------------------------
        cursor.execute(
            "SELECT simulation FROM teams WHERE team_id = ?",
            (team_id,)
        )
        result = cursor.fetchone()

        if result and result[0]:
            simulation = json.loads(result[0])
            # Fix production_plan keys after JSON load
            if simulation.get("production_plan"):
                simulation["production_plan"] = {
                    int(k): v for k, v in simulation["production_plan"].items()
                }

        team_count = len(teams)
        team_financials = build_team_financials(session_id)

        # ---------------------------------------------
        # BUILD MONTHLY TEAM RESULTS FOR DASHBOARD
        # ---------------------------------------------

        monthly_results.clear()

        for month in range(1, total_months + 1):
            monthly_results[month] = []

        for team_id, team_name, password, meta_blob in raw_teams:

            meta = json.loads(meta_blob) if meta_blob else {}

            cursor.execute(
                "SELECT simulation FROM teams WHERE team_id = ?",
                (team_id,)
            )
            result = cursor.fetchone()

            if result and result[0]:
                simulation = json.loads(result[0])

                history = simulation.get("history", [])

                for report in history:

                    month = report["month"]

                    monthly_results[month].append({
                    "team": team_name,
                    "auto_built": meta.get("auto_built", False),
                    "auto_submitted": month in meta.get("auto_submitted_months", []),
                    "units_produced": report["units_produced"],
                    "units_sold": report["units_sold"],
                    "revenue": report["revenue"],
                    "total_cost": report["total_cost"],
                    "profit": report["profit"]
                    })

    conn.close()

    return templates.TemplateResponse(
        "teacher_dashboard.html",
        {
            "request": request,
            "teams": teams,
            "team_count": team_count,
            "user": user,
            "active_session": active_session,
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


@app.post("/delete-team/{team_id}")
def delete_team_route(team_id: str, user=Depends(get_current_user)):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    delete_team(team_id)
    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# TEAM DASHBOARD
# ============================================================

@app.get("/team-dashboard", response_class=HTMLResponse)
def team_dashboard(request: Request, user=Depends(get_current_user)):

    if not user or user["role"] != "team":
        return RedirectResponse("/", status_code=303)

    from database import get_active_session, get_connection
    import json

    import ingredients_engine as ie
    import production_process as pp
    import factory_engine as fe
    from factory_engine import calculate_utilities_cost

    # --------------------------------------------------
    # SESSION DATA
    # --------------------------------------------------

    active_session = get_active_session()

    competitive_mode = False
    team_financials = []

    if active_session:

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT competitive_mode
            FROM simulation_sessions
            WHERE session_id = ?
        """, (active_session[0],))

        result = cursor.fetchone()

        if result and result[0]:
            competitive_mode = True

        team_financials = build_team_financials(active_session[0])

        conn.close()

    # --------------------------------------------------
    # TEAM DATA
    # --------------------------------------------------

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT team_name, simulation, meta FROM teams WHERE team_id = ?",
        (user["team_id"],)
    )

    team = cursor.fetchone()
    conn.close()

    simulation = None
    meta = {}
    team_name = ""

    if team:
        team_name, sim_blob, meta_blob = team

        simulation = json.loads(sim_blob) if sim_blob and sim_blob.strip() else None
        meta = json.loads(meta_blob) if meta_blob else {}

        # ------------------------------------------
        # Compatibility fixes for older simulations
        # ------------------------------------------

        if simulation:

            # Ensure utilities exists in monthly reports
            if simulation.get("history"):
                for month in simulation["history"]:
                    if "cost_breakdown" in month:
                        month["cost_breakdown"].setdefault("monthly_utilities", 0)

            # Ensure starting_cash exists
            if "starting_cash" not in simulation:
                simulation["starting_cash"] = simulation.get("investment_outstanding", 0)

            # Fix JSON key conversion for production plan
            if simulation.get("production_plan"):
                simulation["production_plan"] = {
                    int(k): v for k, v in simulation["production_plan"].items()
                }

    # --------------------------------------------------
    # BISCUIT LIST (used in production planner)
    # --------------------------------------------------

    biscuit_list = ie.get_all_biscuit_names()

    # --------------------------------------------------
    # FACTORY DATA
    # --------------------------------------------------

    process_limits = []
    utilities_cost = 0
    factory = None

    if simulation and simulation.get("factory"):

        factory = simulation["factory"]

        # ------------------------------------------
        # Backwards compatibility: cost breakdown
        # ------------------------------------------

        if "factory_cost_breakdown" not in simulation:

            simulation["factory_cost_breakdown"] = {
                "wall_cost": fe.calculate_wall_cost(factory),
                "floor_cost": fe.calculate_floor_cost(factory),
                "roof_cost": fe.calculate_roof_cost(factory),
                "fixtures_cost": fe.calculate_fixture_cost(factory),
                "utilities_cost": fe.calculate_utilities_cost(factory)
            }

        # ------------------------------------------
        # Utilities cost for template
        # ------------------------------------------

        utilities_cost = calculate_utilities_cost(factory)

        # ------------------------------------------
        # Production process limits
        # ------------------------------------------

        for line in factory.get("lines", []):
            process_type = line["process_type"]
            limits = pp.get_process_limits(process_type)
            process_limits.append(limits)

    # --------------------------------------------------
    # RENDER DASHBOARD
    # --------------------------------------------------

    return templates.TemplateResponse(
        "team_dashboard.html",
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
# LOGOUT
# ============================================================

@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    return response

# ============================================================
# SETUP PHASE
# ============================================================

@app.post("/end-setup-phase")
def end_setup_phase(user=Depends(get_current_user)):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    from database import get_active_session
    import decision_engine as de
    import json

    active_session = get_active_session()
    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, meta
        FROM teams
        WHERE role = 'team' AND session_id = ?
    """, (session_id,))

    teams = cursor.fetchall()

    from Simulation_manager import SimulationManager
    manager = SimulationManager()

    for team_id, meta_blob in teams:

        meta = json.loads(meta_blob) if meta_blob else {}

        # -------------------------------------------------
        # TEAM DID NOT SUBMIT SETUP → AUTO BUILD
        # -------------------------------------------------
        if not meta.get("setup_complete"):

            state, message = de.create_simulation_from_initial_decisions(
                manager.default_setup
            )

            if state is None:
                print("DEFAULT BUILD FAILED:", message)

                # Mark as auto-built but no simulation saved
                meta["setup_complete"] = True
                meta["auto_built"] = True
                meta["submitted"] = True

            else:
                print("AUTO BUILT STATE:", state)  # DEBUG

                cursor.execute(
                    "UPDATE teams SET simulation = ? WHERE team_id = ?",
                    (json.dumps(state), team_id)
                )

                meta["setup_complete"] = True
                meta["auto_built"] = True
                meta["submitted"] = True

        # -------------------------------------------------
        # TEAM DID SUBMIT SETUP
        # -------------------------------------------------
        else:
            meta["auto_built"] = False
            meta["submitted"] = True

        # Always update meta
        cursor.execute(
            "UPDATE teams SET meta = ? WHERE team_id = ?",
            (json.dumps(meta), team_id)
        )

    # -------------------------------------------------
    # Move session into active phase
    # -------------------------------------------------
    cursor.execute("""
        UPDATE simulation_sessions
        SET status = 'active',
            current_month = 1
        WHERE session_id = ?
    """, (session_id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)

# ============================================================
# TEAM SUBMIT DECISIONS
# ============================================================

@app.post("/submit-decisions")
async def submit_decisions(request: Request, user=Depends(get_current_user)):

    if not user or user["role"] != "team":
        return RedirectResponse("/", status_code=303)

    from database import get_active_session
    from decision_engine import apply_student_decisions
    import json

    active_session = get_active_session()

    if not active_session:
        return RedirectResponse("/team-dashboard", status_code=303)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT simulation, meta FROM teams WHERE team_id = ?",
        (user["team_id"],)
    )

    result = cursor.fetchone()

    if not result:
        conn.close()
        return RedirectResponse("/team-dashboard", status_code=303)

    state = json.loads(result[0])
    meta = json.loads(result[1]) if result[1] else {}

    form = await request.form()

    # --------------------------------------------------
    # PARSE QUALITY SYSTEM
    # --------------------------------------------------

    quality_system = form.get("quality_system")

    # --------------------------------------------------
    # PARSE PRODUCTION PLAN
    # --------------------------------------------------

    production_plan = {}

    line_index = 0

    while True:
        line_key = f"line_{line_index}_exists"
        if line_key not in form:
            break

        runs = []
        run_index = 0

        while True:
            biscuit_key = f"line_{line_index}_biscuit_{run_index}"
            units_key = f"line_{line_index}_units_{run_index}"

            if biscuit_key not in form:
                break

            biscuit = form.get(biscuit_key)
            units = form.get(units_key)

            if biscuit and units:
                try:
                    units = float(units)
                    if units > 0:
                        runs.append({
                            "biscuit": biscuit,
                            "units": units
                        })
                except:
                    pass

            run_index += 1

        production_plan[int(line_index)] = runs
        line_index += 1

    decisions = {
        "quality_system": quality_system,
        "production_plan": production_plan
    }
    print("DEBUG production_plan keys:", production_plan.keys())
    print("DEBUG types:", [type(k) for k in production_plan.keys()])
    success, message = apply_student_decisions(state, decisions)

    if not success:

        # Do NOT modify simulation state
        # Instead reload dashboard with the submitted plan

        from database import get_active_session
        import ingredients_engine as ie
        import production_process as pp
        import factory_engine as fe

        active_session = get_active_session()

        biscuit_list = ie.get_all_biscuit_names()

        process_limits = []
        factory = state.get("factory", {})

        for line in factory.get("lines", []):
            process_type = line["process_type"]
            limits = pp.get_process_limits(process_type)
            process_limits.append(limits)

        conn.close()

        return templates.TemplateResponse(
            "team_dashboard.html",
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

    # Save updated state
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

    conn.commit()
    conn.close()

    return RedirectResponse("/team-dashboard", status_code=303)

# ============================================================
# RUN CURRENT MONTH FOR ALL TEAMS
# ============================================================

def run_current_month_for_all_teams(session_id, current_month, scenario):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, team_name, meta
        FROM teams
        WHERE role = 'team' AND session_id = ?
    """, (session_id,))

    teams = cursor.fetchall()

    updated_meta = {}

    for team_id, team_name, meta_blob in teams:

        meta = json.loads(meta_blob) if meta_blob else {}

        cursor.execute(
            "SELECT simulation FROM teams WHERE team_id = ?",
            (team_id,)
        )

        sim_blob = cursor.fetchone()[0]

        if not sim_blob:
            continue

        state = json.loads(sim_blob)

        # Auto-submit logic
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

    # Reset submission flags
    for team_id, meta in updated_meta.items():

        meta["submitted"] = False
        meta["decision_month"] = None

        cursor.execute(
            "UPDATE teams SET meta = ? WHERE team_id = ?",
            (json.dumps(meta), team_id)
        )

    conn.commit()
    conn.close()

# ============================================================
# ADVANCE MONTH
# ============================================================

@app.post("/advance-month")
def advance_month_route(user=Depends(get_current_user)):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    import json
    from database import get_active_session
    from simulation_engine import run_month
    from scenario_engine import DEFAULT_SCENARIO

    active_session = get_active_session()

    if not active_session or active_session[2] != "active":
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]
    current_month = active_session[3]
    total_months = active_session[4]

    if current_month >= total_months and active_session[2] != "active":
        return RedirectResponse("/teacher-dashboard", status_code=303)

    next_month = current_month + 1
    final_month = current_month == total_months

    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------
    # Load scenario
    # --------------------------------------------------

    cursor.execute("""
        SELECT scenario_state
        FROM simulation_sessions
        WHERE session_id = ?
    """, (session_id,))

    scenario_blob = cursor.fetchone()[0]
    scenario_state = json.loads(scenario_blob) if scenario_blob else {}

    scenario = scenario_state.get(str(current_month), DEFAULT_SCENARIO)

    # --------------------------------------------------
    # Fetch teams
    # --------------------------------------------------

    cursor.execute("""
    SELECT team_id, team_name, password, meta
    FROM teams
    WHERE role = 'team' AND session_id = ?
    """, (session_id,))

    teams = cursor.fetchall()

    # --------------------------------------------------
    # Month 1 rule: everyone must submit
    # --------------------------------------------------

    missing_teams = []

    for team_id, team_name, password, meta_blob in teams:

        meta = json.loads(meta_blob) if meta_blob else {}

        # Check if team submitted for this month
        if meta.get("decision_month") != current_month:
            missing_teams.append(team_name)

    # --------------------------------------------------
    # Month 1 rule ONLY: block advance
    # --------------------------------------------------

    if current_month == 1 and missing_teams:

        conn.close()

        missing_string = ",".join(missing_teams)

        return RedirectResponse(
            f"/teacher-dashboard?missing={missing_string}",
            status_code=303
        )
# Close connection before running simulation
    conn.close()

# Run month simulation for all teams
    run_current_month_for_all_teams(session_id, current_month, scenario)

# Reopen connection to update session state
    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------
    # Advance or Finish Session
    # --------------------------------------------------

    if final_month:

        # Final month completed → finish the session
        cursor.execute("""
            UPDATE simulation_sessions
            SET status = 'finished'
            WHERE session_id = ?
        """, (session_id,))

    else:

        # Normal advance
        cursor.execute("""
            UPDATE simulation_sessions
            SET current_month = ?
            WHERE session_id = ?
        """, (next_month, session_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)

#--------------------------------
#FACTORY SETUP
#--------------------------------

@app.get("/factory-setup", response_class=HTMLResponse)
def factory_setup_page(request: Request, user=Depends(get_current_user)):

    if not user or user["role"] != "team":
        return RedirectResponse("/", status_code=303)

    from database import get_active_session

    active_session = get_active_session()

    # Only allow during setup phase
    if not active_session or active_session[2] != "setup":
        return RedirectResponse("/team-dashboard", status_code=303)

    conn = get_connection()
    cursor = conn.cursor()

    # Get meta
    cursor.execute(
        "SELECT team_name, meta FROM teams WHERE team_id = ?",
        (user["team_id"],)
    )

    result = cursor.fetchone()

    if not result:
        conn.close()
        return RedirectResponse("/team-dashboard", status_code=303)

    team_name, meta_blob = result
    meta = json.loads(meta_blob) if meta_blob else {}

    if meta.get("setup_complete"):
        conn.close()
        return RedirectResponse("/team-dashboard", status_code=303)

    conn.close()

    return templates.TemplateResponse(
        "factory_setup.html",
        {
            "request": request,
            "team_name": team_name,
            "user": user
        }
    )


@app.post("/factory-setup")
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
        return RedirectResponse("/", status_code=303)

    import decision_engine as de
    import json

    conn = get_connection()
    cursor = conn.cursor()
    team_id = user["team_id"]

    # --------------------------------------------------
    # Build setup input format (what decision_engine expects)
    # --------------------------------------------------
    production_lines = []

    production_lines += ["job"] * job
    production_lines += ["batch"] * batch
    production_lines += ["cell"] * cell
    production_lines += ["flow"] * flow

    setup_data = {
    "starting_cash": starting_cash,
    "factory": {
        "length_m": length_m,
        "width_m": width_m,

        "wall_blocks": {
            "small": wall_small,
            "medium": wall_medium,
            "large": wall_large
        },

        "fixtures": {
            "industrial_door": industrial_door,
            "pedestrian_door": pedestrian_door,
            "window": window
        },

        "floor_slabs": floor_slabs,
        "roof_panels": roof_panels,
        "production_lines": production_lines,

        # 🔥 THIS IS THE FIX
        "quality_system": quality_system
    }
}

    # --------------------------------------------------
    # Send through decision engine
    # --------------------------------------------------
    state, message = de.create_simulation_from_initial_decisions(setup_data)

    # --------------------------------------------------
    # IF VALIDATION FAILED
    # --------------------------------------------------

    if state is None:

        # Get team name BEFORE closing DB
        cursor.execute(
            "SELECT team_name FROM teams WHERE team_id = ?",
            (team_id,)
        )
        team_name = cursor.fetchone()[0]

        conn.close()

        mapping = {
            "floor_slabs": "Floor slabs — not enough",
            "roof_panels": "Roof panels — not enough",
            "wall_blocks": "Wall blocks — not enough",
            "capital": "Investment requested — not enough",
            "space": "Factory space — not enough space for staff/goods movements and wellfare facilities",
            "doors": "Doors — not enough",
            "lines": "Production lines — not enough",
            "quality": "Quality system — not selected"
        }

        friendly_messages = []

        if isinstance(message, list):
            for error in message:
                if error in mapping:
                    friendly_messages.append(mapping[error])
        else:
            friendly_messages.append(str(message))

        return templates.TemplateResponse(
            "factory_setup.html",
            {
                "request": request,
                "team_name": team_name,
                "user": user,
                "errors": friendly_messages,
                "form_data": setup_data
            }
        )

    # --------------------------------------------------
    # IF VALIDATION PASSED
    # --------------------------------------------------

    from database import get_active_session
    active_session = get_active_session()
    total_months = active_session[4]

    state["max_months"] = total_months

    # --------------------------------------------------
    # Save PROCESSED simulation state (NOT setup_data)
    # --------------------------------------------------
    cursor.execute(
        "UPDATE teams SET simulation = ? WHERE team_id = ?",
        (json.dumps(state), team_id)
    )

    # Update meta
    cursor.execute(
        "SELECT meta FROM teams WHERE team_id = ?",
        (team_id,)
    )

    meta_blob = cursor.fetchone()[0]
    meta = json.loads(meta_blob) if meta_blob else {}

    meta["submitted"] = True
    meta["setup_complete"] = True
    meta["auto_built"] = False

    cursor.execute(
        "UPDATE teams SET meta = ? WHERE team_id = ?",
        (json.dumps(meta), team_id)
    )

    conn.commit()
    conn.close()

    return RedirectResponse("/team-dashboard", status_code=303)

#--------------------------
# TEACHER RENAME
#--------------------------

@app.post("/rename-team")
def rename_team(
    team_id: str = Form(...),
    new_name: str = Form(...),
    user=Depends(get_current_user)
):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE teams SET team_name = ? WHERE team_id = ?",
        (new_name, team_id)
    )

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)

#-----------------------------------------------
# SCENARIO STATE
#-----------------------------------------------

@app.post("/update-scenario")
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
        return RedirectResponse("/", status_code=303)

    conn = get_connection()
    cursor = conn.cursor()

    active_session = get_active_session()
    session_id = active_session[0]
    current_month = active_session[3]

    # Lock protection
    if month < current_month:
        conn.close()
        return RedirectResponse("/teacher-dashboard", status_code=303)

    cursor.execute("""
        SELECT scenario_state
        FROM simulation_sessions
        WHERE session_id = ?
    """, (session_id,))

    result = cursor.fetchone()
    scenario_state = json.loads(result[0]) if result and result[0] else {}

    scenario_state[str(month)] = {
        "name": name,
        "scrap_rate": {
            "qc": scrap_qc,
            "qa": scrap_qa,
            "tqm": scrap_tqm
        },
        "machine_breakdown": machine_breakdown,
        "employee_strike": employee_strike,
        "ingredient_multiplier": ingredient_multiplier,
        "shipping_multiplier": shipping_multiplier,
        "sales_price_multiplier": sales_price_multiplier,
        "demand_multiplier": demand_multiplier,
        "extra_fixed_cost": extra_fixed_cost
    }

    cursor.execute("""
        UPDATE simulation_sessions
        SET scenario_state = ?
        WHERE session_id = ?
    """, (json.dumps(scenario_state), session_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)

# ============================================================
# END SESSION EARLY
# ============================================================

@app.post("/end-session")
def end_session(user=Depends(get_current_user)):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    from simulation_engine import run_month
    import json

    active_session = get_active_session()

    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]
    current_month = active_session[3]

    conn = get_connection()
    cursor = conn.cursor()

    # Load scenario
    cursor.execute("""
        SELECT scenario_state
        FROM simulation_sessions
        WHERE session_id = ?
    """, (session_id,))

    result = cursor.fetchone()
    scenario_state = json.loads(result[0]) if result and result[0] else {}

    scenario = scenario_state.get(str(current_month), DEFAULT_SCENARIO)

    conn.close()

    # Run simulation
    run_current_month_for_all_teams(session_id, current_month, scenario)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE simulation_sessions
    SET status = 'finished',
        current_month = ?
    WHERE session_id = ?
    """, (current_month, session_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)

# ============================================================
# DELETE SESSION
# ============================================================

@app.post("/delete-session")
def delete_session(user=Depends(get_current_user)):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    conn = get_connection()
    cursor = conn.cursor()

    active_session = get_active_session()

    if not active_session:
        conn.close()
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]

    # Delete teams in this session
    cursor.execute("""
        DELETE FROM teams
        WHERE session_id = ?
        AND role = 'team'
    """, (session_id,))

    # Delete the session itself
    cursor.execute("""
        DELETE FROM simulation_sessions
        WHERE session_id = ?
    """, (session_id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# MAKE SESSION COMPETITIVE
# ============================================================

@app.post("/make-competitive")
def make_competitive(user=Depends(get_current_user)):

    if not user or user["role"] != "teacher":
        return RedirectResponse("/", status_code=303)

    active_session = get_active_session()

    if not active_session:
        return RedirectResponse("/teacher-dashboard", status_code=303)

    session_id = active_session[0]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE simulation_sessions
        SET competitive_mode = 1
        WHERE session_id = ?
    """, (session_id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/teacher-dashboard", status_code=303)


# ============================================================
# CREATE PDF REPORTS - Placeholder
# ============================================================

@app.post("/create-pdfs")
def create_pdfs():

    session = get_active_session()

    if not session:
        return {"error": "No active session found"}

    session_id = session[0]

    from pdf_engine import generate_all_reports, create_zip

    files = generate_all_reports(session_id)

    zip_path = create_zip(files)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="simulation_reports.zip"
    )