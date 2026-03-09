from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
import os
import json
import zipfile
from datetime import datetime
from database import get_connection

def create_reports_folder():
    folder = "temp_reports"

    if not os.path.exists(folder):
        os.makedirs(folder)

    return folder

def get_teams_for_session(session_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_id, team_name, simulation
        FROM teams
        WHERE role = 'team' AND session_id = ?
    """, (session_id,))

    rows = cursor.fetchall()
    conn.close()

    teams = []

    for team_id, team_name, sim_blob in rows:

        simulation = json.loads(sim_blob) if sim_blob else {}

        teams.append({
            "team_id": team_id,
            "team_name": team_name,
            "simulation": simulation
        })

    return teams

def generate_teacher_report(session_id, folder):

    teams = get_teams_for_session(session_id)

    pdf_path = os.path.join(folder, "teacher_report.pdf")

    styles = getSampleStyleSheet()
    elements = []

    # -------------------------
    # Title
    # -------------------------

    elements.append(Paragraph("Biscuit Factory Simulator", styles['Title']))
    elements.append(Paragraph("Teacher Report", styles['Heading2']))
    elements.append(Spacer(1,20))

    # -------------------------
    # Leaderboard
    # -------------------------

    elements.append(Paragraph("Class Leaderboard", styles['Heading2']))

    leaderboard = [["Team","Profit","Cash","Remaining Investment"]]

    for team in teams:

        sim = team["simulation"]

        leaderboard.append([
            team["team_name"],
            f"£{sim.get('cumulative_profit',0):,.0f}",
            f"£{sim.get('cash',0):,.0f}",
            f"£{sim.get('investment_outstanding',0):,.0f}"
        ])

    elements.append(Table(leaderboard))
    elements.append(Spacer(1,20))

    # -------------------------
    # Production Summary
    # -------------------------

    elements.append(Paragraph("Production Summary", styles['Heading2']))

    production_data = [["Team","Produced","Sold","Wastage %"]]

    for team in teams:

        sim = team["simulation"]
        history = sim.get("history", [])

        total_produced = 0
        total_sold = 0

        for month in history:
            total_produced += month["units_produced"]
            total_sold += month["units_sold"]

        wastage = 0
        if total_produced > 0:
            wastage = ((total_produced - total_sold) / total_produced) * 100

        production_data.append([
            team["team_name"],
            int(total_produced),
            int(total_sold),
            f"{wastage:.1f}%"
        ])

    elements.append(Table(production_data))
    elements.append(Spacer(1,20))

    # -------------------------
    # Monthly Scenarios
    # -------------------------

    elements.append(Paragraph("Monthly Scenarios", styles['Heading2']))

    scenario_table = [["Month","Scenario"]]

    # Use first team to read scenarios
    if teams:

        history = teams[0]["simulation"].get("history", [])

        for month in history:

            scenario_table.append([
                month["month"],
                month["scenario"]
            ])

    elements.append(Table(scenario_table))

    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    doc.build(elements)

    return pdf_path

def generate_team_report(team, folder):

    sim = team["simulation"]
    history = sim.get("history", [])
    factory = sim.get("factory", {})

    filename = f"team_{team['team_name']}.pdf"
    pdf_path = os.path.join(folder, filename)

    styles = getSampleStyleSheet()
    elements = []

    # -------------------------
    # Title
    # -------------------------

    elements.append(Paragraph(f"Team Report — {team['team_name']}", styles['Title']))
    elements.append(Spacer(1,20))

    # -------------------------
    # Factory Setup
    # -------------------------

    elements.append(Paragraph("Factory Setup", styles['Heading2']))

    lines = factory.get("lines", [])
    line_types = [line["process_type"] for line in lines]

    factory_data = [
        ["Factory Size", f"{factory.get('length_m',0)}m x {factory.get('width_m',0)}m"],
        ["Quality System", factory.get("quality_system","None")],
        ["Production Lines", ", ".join(line_types) if line_types else "None"],
        ["Floor Slabs", factory.get("floor_slabs_purchased",0)],
        ["Roof Panels", factory.get("roof_panels_purchased",0)]
    ]

    elements.append(Table(factory_data))
    elements.append(Spacer(1,20))

    # -------------------------
    # Financial Summary
    # -------------------------

    elements.append(Paragraph("Financial Summary", styles['Heading2']))

    summary_data = [
        ["Starting Investment", f"£{sim.get('starting_cash',0):,.0f}"],
        ["Total Profit", f"£{sim.get('cumulative_profit',0):,.0f}"],
        ["Cash", f"£{sim.get('cash',0):,.0f}"],
        ["Remaining Investment", f"£{sim.get('investment_outstanding',0):,.0f}"]
    ]

    elements.append(Table(summary_data))
    elements.append(Spacer(1,20))

    # -------------------------
    # Monthly Performance
    # -------------------------

    elements.append(Paragraph("Monthly Performance", styles['Heading2']))

    table_data = [["Month","Scenario","Produced","Sold","Revenue","Profit"]]

    total_produced = 0
    total_sold = 0

    for month in history:

        produced = month["units_produced"]
        sold = month["units_sold"]

        total_produced += produced
        total_sold += sold

        table_data.append([
            month["month"],
            month["scenario"],
            int(produced),
            int(sold),
            f"£{month['revenue']:,.0f}",
            f"£{month['profit']:,.0f}"
        ])

    elements.append(Table(table_data))
    elements.append(Spacer(1,20))

    # -------------------------
    # Production Totals
    # -------------------------

    wastage = 0
    if total_produced > 0:
        wastage = ((total_produced - total_sold) / total_produced) * 100

    elements.append(Paragraph("Production Totals", styles['Heading2']))

    totals = [
        ["Total Produced", int(total_produced)],
        ["Total Sold", int(total_sold)],
        ["Wastage %", f"{wastage:.1f}%"]
    ]

    elements.append(Table(totals))

    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    doc.build(elements)

    return pdf_path

def generate_all_reports(session_id):

    folder = create_reports_folder()

    teams = get_teams_for_session(session_id)

    files = []

    teacher_pdf = generate_teacher_report(session_id, folder)
    files.append(teacher_pdf)

    for team in teams:

        team_pdf = generate_team_report(team, folder)
        files.append(team_pdf)

    return files

def create_zip(files):

    zip_path = "simulation_reports.zip"

    with zipfile.ZipFile(zip_path, "w") as zipf:

        for file in files:
            zipf.write(file, os.path.basename(file))

    return zip_path