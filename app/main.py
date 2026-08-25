from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="QA Toolbox")

Path("app/static").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
