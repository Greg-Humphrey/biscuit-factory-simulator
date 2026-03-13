import sqlite3
import json
import uuid
from datetime import datetime

DB_NAME = "simulator.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        team_id TEXT PRIMARY KEY,
        team_name TEXT,
        password TEXT,
        role TEXT,
        simulation TEXT,
        meta TEXT,
        current_month INTEGER,
        session_id TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS simulation_sessions (
        session_id TEXT PRIMARY KEY,
        session_name TEXT,
        status TEXT,
        current_month INTEGER,
        total_months INTEGER,
        scenario_state TEXT,
        competitive_mode INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)
    # Ensure teacher account exists
    cursor.execute("SELECT * FROM teams WHERE team_name = ?", ("teacher",))
    teacher = cursor.fetchone()

    if not teacher:
        cursor.execute("""
            INSERT INTO teams (team_id, team_name, password, role, simulation, meta, current_month)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "teacher",
            "teacher",
            "999",
            "teacher",
            json.dumps({}),
            json.dumps({}),
            1
        ))

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# SAVE TEAM (CRITICAL FIX: preserve password + role)
# ---------------------------------------------------------

def save_team(team_id, team_name, simulation_object, meta_object, current_month):

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Preserve password + role
    cursor.execute("SELECT password, role FROM teams WHERE team_id = ?", (team_id,))
    existing = cursor.fetchone()

    if existing:
        password, role = existing
    else:
        password = "123"  # default simple password
        role = "team"

    serialized_simulation = json.dumps(simulation_object) if simulation_object else None
    serialized_meta = json.dumps(meta_object) if meta_object else None

    cursor.execute("""
        INSERT OR REPLACE INTO teams 
        (team_id, team_name, password, role, simulation, meta, current_month)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        team_id,
        team_name,
        password,
        role,
        serialized_simulation,
        serialized_meta,
        current_month
    ))

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# LOAD ALL TEAMS (FIXED LOOP + SAFETY)
# ---------------------------------------------------------

def load_all_teams():

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, team_name, simulation, meta, current_month
        FROM teams
    """)

    rows = cursor.fetchall()
    conn.close()

    teams = {}
    current_month = 1

    for team_id, team_name, sim_blob, meta_blob, month in rows:

        simulation = json.loads(sim_blob) if sim_blob else None
        meta = json.loads(meta_blob) if meta_blob else {}

        # Ensure meta always has required keys
        if "phase" not in meta:
            meta["phase"] = "operating"

        if "submitted" not in meta:
            meta["submitted"] = False

        teams[team_id] = {
            "team_name": team_name,
            "simulation": simulation,
            "meta": meta
        }

        current_month = month

    return teams, current_month

#--------------------------
# Delete Team
#--------------------------

def delete_team(team_id: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM teams
        WHERE team_id = ? AND role = 'team'
    """, (team_id,))

    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, team_name, password, role
        FROM teams
    """)

    users = cursor.fetchall()
    conn.close()

    return users

def get_all_teams_for_dashboard():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, team_name, password
        FROM teams
        WHERE role = 'team'
    """)

    teams = cursor.fetchall()
    conn.close()

    return teams

def get_connection():
    return sqlite3.connect(DB_NAME)

#--------------------
#Session Helper Functions
#--------------------

def get_active_session():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT session_id, session_name, status, current_month, total_months
    FROM simulation_sessions
    ORDER BY created_at DESC
    LIMIT 1
    """)

    session = cursor.fetchone()

    conn.close()
    return session

def create_new_session(session_name, total_months):

    import json
    from datetime import datetime
    import uuid

    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------
    # Deactivate any existing active session
    # --------------------------------------------------
    cursor.execute("""
        UPDATE simulation_sessions
        SET status = 'finished'
        WHERE status != 'finished'
    """)

    session_id = str(uuid.uuid4())

    # --------------------------------------------------
    # NEW BEHAVIOUR:
    # Start with EMPTY scenario_state
    # DEFAULT_SCENARIO will be used lazily at runtime
    # --------------------------------------------------
    scenario_state = {}

    # --------------------------------------------------
    # Insert new session
    # --------------------------------------------------
    cursor.execute("""
        INSERT INTO simulation_sessions (
            session_id,
            session_name,
            status,
            current_month,
            total_months,
            scenario_state,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        session_name,
        "setup",
        0,
        total_months,
        json.dumps(scenario_state),  # 🔥 empty dict
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()

def increment_session_month():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE simulation_sessions
        SET current_month = current_month + 1
        WHERE status = 'active'
    """)

    conn.commit()
    conn.close()

def save_team_simulation_state(team_id, state):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE teams
        SET simulation = ?
        WHERE team_id = ?
    """, (json.dumps(state), team_id))

    conn.commit()
    conn.close()


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
                "margin": 0,
                "overheads": 0,
            })

    conn.close()

    return team_financials