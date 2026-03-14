import os
import json
import zipfile
from datetime import datetime
from database import get_connection, get_db, get_active_session, build_team_financials
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
from scenario_engine import DEFAULT_SCENARIO

env = Environment(loader=FileSystemLoader("templates"))

def generate_teacher_pdf(session_data, folder):

    template = env.get_template("biscuit_factory/teacher_dashboard_pdf.html")

    html = template.render(**session_data)

    pdf_path = os.path.join(folder, "teacher_dashboard.pdf")

    HTML(string=html, base_url=os.path.abspath(".")).write_pdf(pdf_path)

    return pdf_path

def generate_team_pdf(team_data, folder):

    template = env.get_template("biscuit_factory/team_dashboard_pdf.html")

    html = template.render(**team_data)

    filename = f"{team_data['team_name']}_dashboard.pdf"
    pdf_path = os.path.join(folder, filename)

    HTML(string=html, base_url=os.path.abspath(".")).write_pdf(pdf_path)

    return pdf_path

def create_reports_folder():
    folder = "temp_reports"

    if not os.path.exists(folder):
        os.makedirs(folder)

    return folder

def get_teams_for_session(session_id):

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT team_id, team_name, simulation
            FROM teams
            WHERE role = 'team' AND session_id = ?
        """, (session_id,))

        rows = cursor.fetchall()

    teams = []

    for team_id, team_name, sim_blob in rows:

        simulation = json.loads(sim_blob) if sim_blob else {}

        teams.append({
            "team_id": team_id,
            "team_name": team_name,
            "simulation": simulation
        })

    return teams

def build_teacher_dashboard_data(session_id):

    active_session = get_active_session()

    current_month = active_session[3]
    total_months = active_session[4]

    with get_db() as conn:
        cursor = conn.cursor()

        # ----------------------------
        # Load scenarios
        # ----------------------------

        cursor.execute("""
            SELECT scenario_state
            FROM simulation_sessions
            WHERE session_id = ?
        """, (session_id,))

        result = cursor.fetchone()

        scenario_state = json.loads(result[0]) if result and result[0] else {}

        scenarios = {}

        for month in range(1, total_months + 1):

            scenario = DEFAULT_SCENARIO.copy()

            override = scenario_state.get(str(month))

            if override:
                scenario.update(override)

            scenarios[str(month)] = scenario

        # ----------------------------
        # Teams
        # ----------------------------

        cursor.execute("""
            SELECT team_id, team_name, password, meta
            FROM teams
            WHERE role='team' AND session_id=?
        """, (session_id,))

        raw_teams = cursor.fetchall()

        teams = []

        for team_id, team_name, password, meta_blob in raw_teams:

            meta = json.loads(meta_blob) if meta_blob else {}

            auto_built = meta.get("auto_built", False)

            teams.append((team_id, team_name, password, auto_built))

        team_count = len(teams)

        # ----------------------------
        # Financials
        # ----------------------------

        team_financials = build_team_financials(session_id)

        # ----------------------------
        # Monthly results
        # ----------------------------

        monthly_results = {}

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
                        "quality_system": report.get("quality_system", ""),
                        "units_produced": report["units_produced"],
                        "units_sold": report["units_sold"],
                        "revenue": report["revenue"],
                        "total_cost": report["total_cost"],
                        "profit": report["profit"]
                    })

    return {
        "active_session": active_session,
        "teams": teams,
        "team_count": team_count,
        "team_financials": team_financials,
        "scenarios": scenarios,
        "current_month": current_month,
        "total_months": total_months,
        "monthly_results": monthly_results
    }

def build_team_dashboard_data(team):

    active_session = get_active_session()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT competitive_mode FROM simulation_sessions WHERE session_id = ?", (active_session[0],))
        row = cursor.fetchone()
    competitive_mode = bool(row[0]) if row else False

    return {
        "team_name": team["team_name"],
        "simulation": team["simulation"],
        "active_session": active_session,
        "team_financials": build_team_financials(active_session[0]),
        "current_team_id": team["team_id"],
        "competitive_mode": competitive_mode
    }

def generate_all_reports(session_id):

    folder = create_reports_folder()

    teams = get_teams_for_session(session_id)

    files = []

    # Teacher PDF
    teacher_data = build_teacher_dashboard_data(session_id)

    teacher_pdf = generate_teacher_pdf(teacher_data, folder)

    files.append(teacher_pdf)

    # Team PDFs
    for team in teams:

        team_data = build_team_dashboard_data(team)

        team_pdf = generate_team_pdf(team_data, folder)

        files.append(team_pdf)

    return files

def create_zip(files):

    zip_path = "simulation_reports.zip"

    with zipfile.ZipFile(zip_path, "w") as zipf:

        for file in files:
            zipf.write(file, os.path.basename(file))

    return zip_path