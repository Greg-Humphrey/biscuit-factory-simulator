from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import init_db
from routers import platform, biscuit_factory

app = FastAPI()
init_db()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(platform.router)
app.include_router(biscuit_factory.router)
