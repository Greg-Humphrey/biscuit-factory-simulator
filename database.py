import sqlite3
import json
import uuid
from datetime import datetime

import os
DB_NAME = os.environ.get("DB_PATH", "/data/simulator.db")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schools (
        school_id TEXT PRIMARY KEY,
        school_name TEXT NOT NULL,
        contact_email TEXT,
        licence_type TEXT DEFAULT 'trial',
        licence_expiry TEXT,
        max_sessions INTEGER DEFAULT 3,
        notes TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        team_id TEXT PRIMARY KEY,
        team_name TEXT,
        password TEXT,
        role TEXT,
        simulation TEXT,
        meta TEXT,
        current_month INTEGER,
        session_id TEXT,
        school_id TEXT REFERENCES schools(school_id)
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
    # Migrate: add columns to teams if they don't exist yet
    cursor.execute("PRAGMA table_info(teams)")
    columns = [row[1] for row in cursor.fetchall()]
    if "school_id" not in columns:
        cursor.execute("ALTER TABLE teams ADD COLUMN school_id TEXT REFERENCES schools(school_id)")
    if "email" not in columns:
        cursor.execute("ALTER TABLE teams ADD COLUMN email TEXT")

    # Migrate: add columns to simulation_sessions if they don't exist yet
    cursor.execute("PRAGMA table_info(simulation_sessions)")
    session_columns = [row[1] for row in cursor.fetchall()]
    if "teacher_id" not in session_columns:
        cursor.execute("ALTER TABLE simulation_sessions ADD COLUMN teacher_id TEXT")
    if "join_code" not in session_columns:
        cursor.execute("ALTER TABLE simulation_sessions ADD COLUMN join_code TEXT")

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

def _generate_join_code():
    import random, string
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def create_new_session(session_name, total_months, teacher_id=None):

    conn = get_connection()
    cursor = conn.cursor()

    # Deactivate any existing active session for this teacher
    if teacher_id:
        cursor.execute("""
            UPDATE simulation_sessions
            SET status = 'finished'
            WHERE teacher_id = ? AND status != 'finished'
        """, (teacher_id,))
    else:
        cursor.execute("""
            UPDATE simulation_sessions
            SET status = 'finished'
            WHERE status != 'finished'
        """)

    session_id = str(uuid.uuid4())

    # Generate a unique 6-character join code
    join_code = _generate_join_code()
    cursor.execute("SELECT session_id FROM simulation_sessions WHERE join_code = ?", (join_code,))
    while cursor.fetchone():
        join_code = _generate_join_code()
        cursor.execute("SELECT session_id FROM simulation_sessions WHERE join_code = ?", (join_code,))

    cursor.execute("""
        INSERT INTO simulation_sessions (
            session_id,
            session_name,
            status,
            current_month,
            total_months,
            scenario_state,
            created_at,
            teacher_id,
            join_code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        session_name,
        "setup",
        0,
        total_months,
        json.dumps({}),
        datetime.utcnow().isoformat(),
        teacher_id,
        join_code
    ))

    conn.commit()
    conn.close()
    return join_code

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


# ---------------------------------------------------------
# TEACHER ACCOUNTS
# ---------------------------------------------------------

def register_teacher(name, email, school_name, password):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT team_id FROM teams WHERE email = ? AND role = 'teacher'", (email,))
    if cursor.fetchone():
        conn.close()
        return None, "An account with that email already exists."

    school_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO schools (school_id, school_name, licence_type, max_sessions, created_at)
        VALUES (?, ?, 'trial', 3, ?)
    """, (school_id, school_name, datetime.utcnow().isoformat()))

    teacher_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO teams (team_id, team_name, email, password, role, simulation, meta, current_month, school_id)
        VALUES (?, ?, ?, ?, 'teacher', ?, ?, 0, ?)
    """, (teacher_id, name, email, password, json.dumps({}), json.dumps({}), school_id))

    conn.commit()
    conn.close()
    return teacher_id, None


def authenticate_teacher_by_email(email, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT team_id, team_name FROM teams WHERE email = ? AND password = ? AND role = 'teacher'",
        (email, password)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"team_id": row[0], "team_name": row[1], "role": "teacher"}
    return None


def get_active_session_for_teacher(teacher_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, session_name, status, current_month, total_months, join_code
        FROM simulation_sessions
        WHERE teacher_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (teacher_id,))
    session = cursor.fetchone()
    conn.close()
    return session


def get_session_by_join_code(join_code):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, session_name, status, current_month, total_months, join_code, teacher_id
        FROM simulation_sessions
        WHERE join_code = ?
    """, (join_code.upper(),))
    session = cursor.fetchone()
    conn.close()
    return session


def get_session_for_team(team_id):
    """Get the session a team belongs to, via their stored session_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.session_id, s.session_name, s.status, s.current_month, s.total_months, s.join_code
        FROM teams t
        JOIN simulation_sessions s ON t.session_id = s.session_id
        WHERE t.team_id = ?
    """, (team_id,))
    session = cursor.fetchone()
    conn.close()
    return session


# ---------------------------------------------------------
# SCHOOLS / LICENSING
# ---------------------------------------------------------

def create_school(school_name, contact_email=None, licence_type="trial", licence_expiry=None, max_sessions=3, notes=None):
    conn = get_connection()
    cursor = conn.cursor()
    school_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO schools (school_id, school_name, contact_email, licence_type, licence_expiry, max_sessions, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (school_id, school_name, contact_email, licence_type, licence_expiry, max_sessions, notes, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return school_id


def get_all_schools():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT school_id, school_name, contact_email, licence_type, licence_expiry, max_sessions, notes, created_at
        FROM schools
        ORDER BY school_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "school_id": r[0], "school_name": r[1], "contact_email": r[2],
            "licence_type": r[3], "licence_expiry": r[4], "max_sessions": r[5],
            "notes": r[6], "created_at": r[7]
        }
        for r in rows
    ]


def update_school(school_id, **kwargs):
    allowed = {"school_name", "contact_email", "licence_type", "licence_expiry", "max_sessions", "notes"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    cursor.execute(f"UPDATE schools SET {set_clause} WHERE school_id = ?", (*fields.values(), school_id))
    conn.commit()
    conn.close()


def assign_teacher_to_school(teacher_id, school_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE teams SET school_id = ? WHERE team_id = ? AND role = 'teacher'", (school_id, teacher_id))
    conn.commit()
    conn.close()