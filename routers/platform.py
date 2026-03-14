# ============================================================
# SIMPRENTICE PLATFORM ROUTES
# Auth, Simulator Hub, Student entry
# ============================================================

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import create_access_token, get_current_user, authenticate_user
from templates_config import templates
from database import (
    get_connection,
    get_db,
    register_teacher,
    authenticate_teacher_by_email,
    get_all_sessions_for_teacher,
    count_sessions_for_teacher,
    get_session_by_join_code,
    get_session_for_team,
)

router = APIRouter()


# ============================================================
# MARKETING HOMEPAGE
# ============================================================

@router.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    host = request.headers.get("host", "")
    if host.startswith("sim."):
        return RedirectResponse(url="https://simprentice.com/app")
    user = get_current_user(request)
    return templates.TemplateResponse("platform/marketing/homepage.html", {"request": request, "user": user})


# ============================================================
# SIMULATOR HUB
# ============================================================

@router.get("/hub", response_class=HTMLResponse)
def simulator_hub(request: Request, user=Depends(get_current_user)):
    if not user or user["role"] != "teacher":
        return RedirectResponse("/teacher-login", status_code=303)

    all_sessions = get_all_sessions_for_teacher(user["team_id"])
    session_count = len(all_sessions)
    can_create = session_count < 6

    return templates.TemplateResponse(
        "platform/simulator_hub.html",
        {
            "request": request,
            "user": user,
            "biscuit_sessions": all_sessions,
            "session_count": session_count,
            "can_create": can_create,
            "session_limit": 6,
        }
    )


# ============================================================
# DASHBOARD REDIRECT
# ============================================================

@router.get("/dashboard")
def dashboard(user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/", status_code=303)
    if user["role"] == "teacher":
        return RedirectResponse("/hub", status_code=303)
    return RedirectResponse("/team-dashboard", status_code=303)


# ============================================================
# LOGOUT
# ============================================================

@router.get("/logout")
def logout(request: Request):
    user = get_current_user(request)
    if user and user["role"] == "team":
        session = get_session_for_team(user["team_id"])
        redirect_to = f"/join/{session[5]}" if session else "/student"
    else:
        redirect_to = "/"
    response = RedirectResponse(redirect_to, status_code=303)
    response.delete_cookie("access_token")
    return response


# ============================================================
# TEACHER AUTH
# ============================================================

@router.get("/teacher-login", response_class=HTMLResponse)
def teacher_login_page(request: Request):
    return templates.TemplateResponse("platform/teacher_login.html", {"request": request})


@router.post("/teacher-login")
def teacher_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    user = authenticate_teacher_by_email(email, password)
    if not user:
        return templates.TemplateResponse(
            "platform/teacher_login.html",
            {"request": request, "error": "Email or password not recognised."}
        )
    token = create_access_token(
        {"team_id": user["team_id"], "team_name": user["team_name"], "role": user["role"]}
    )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("access_token", token, httponly=True)
    return response


@router.get("/teacher-register", response_class=HTMLResponse)
def teacher_register_page(request: Request):
    return templates.TemplateResponse("platform/teacher_register.html", {"request": request})


@router.post("/teacher-register")
def teacher_register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    school_name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "platform/teacher_register.html",
            {"request": request, "error": "Passwords do not match."}
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "platform/teacher_register.html",
            {"request": request, "error": "Password must be at least 8 characters."}
        )
    teacher_id, error = register_teacher(name, email, school_name, password)
    if error:
        return templates.TemplateResponse(
            "platform/teacher_register.html",
            {"request": request, "error": error}
        )
    token = create_access_token({"team_id": teacher_id, "team_name": name, "role": "teacher"})
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("access_token", token, httponly=True)
    return response


# ============================================================
# TEAM AUTH
# ============================================================

@router.get("/team-login", response_class=HTMLResponse)
def team_login_page(request: Request):
    return templates.TemplateResponse("platform/team_login.html", {"request": request})


@router.post("/team-login")
def team_login(
    request: Request,
    team_name: str = Form(...),
    password: str = Form(...)
):
    user = authenticate_user(team_name, password)
    if not user or user["role"] != "team":
        return templates.TemplateResponse(
            "platform/team_login.html",
            {"request": request, "error": "Wrong team name or password"}
        )
    token = create_access_token(
        {"team_id": user["team_id"], "team_name": user["team_name"], "role": user["role"]}
    )
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("access_token", token, httponly=True)
    return response


# ============================================================
# STUDENT ENTRY
# ============================================================

@router.get("/student", response_class=HTMLResponse)
def student_entry_page(request: Request):
    return templates.TemplateResponse("platform/student_entry.html", {"request": request})


@router.post("/student")
def student_entry_submit(join_code: str = Form(...)):
    return RedirectResponse(f"/join/{join_code.strip().upper()}", status_code=303)


@router.get("/join/{code}", response_class=HTMLResponse)
def session_landing(request: Request, code: str):
    code = code.upper()
    session = get_session_by_join_code(code)

    if not session:
        return templates.TemplateResponse(
            "platform/student_entry.html",
            {"request": request, "error": "That code wasn't recognised. Check with your teacher."}
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT team_name FROM teams WHERE team_id = ?", (session[6],))
        teacher_row = cursor.fetchone()

    teacher_first_name = ""
    if teacher_row and teacher_row[0]:
        teacher_first_name = teacher_row[0].split()[0]

    return templates.TemplateResponse(
        "platform/session_landing.html",
        {
            "request": request,
            "session_name": session[1],
            "session_status": session[2],
            "teacher_first_name": teacher_first_name,
            "join_code": code,
        }
    )
