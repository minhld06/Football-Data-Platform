import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import leagues, teams, players  # , matches, search  # TEMP: uncommented in Task 8

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Football Data Platform API")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(leagues.router, prefix="/api/leagues", tags=["leagues"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(players.router, prefix="/api/players", tags=["players"])
# app.include_router(matches.router, prefix="/api/matches", tags=["matches"])  # TEMP: uncommented in Task 8
# app.include_router(search.router, prefix="/api/search", tags=["search"])  # TEMP: uncommented in Task 8


@app.get("/api/health")
def health():
    return {"status": "ok"}