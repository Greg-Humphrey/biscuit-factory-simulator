from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Request
from database import get_connection

SECRET_KEY = "super_secret_key_change_this"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600


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
            "team_name": payload.get("team_name"),
            "role": payload.get("role"),
        }
    except JWTError:
        return None


def authenticate_user(team_name: str, password: str):
    """Authenticate student teams by team_name + password."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT team_id, team_name, password, role FROM teams WHERE team_name = ? AND role = 'team'",
        (team_name,)
    )
    user = cursor.fetchone()
    conn.close()
    if user and user[2] == password:
        return {"team_id": user[0], "team_name": user[1], "role": user[3]}
    return None
