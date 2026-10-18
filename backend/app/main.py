from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.patients import router as patients_router
from app.api.staff import router as staff_router
from app.api.station import router as station_router
from app.core.config import settings

app = FastAPI(
    title="QMMC PD1 Proof of Concept",
    version="0.1.0",
    debug=settings.debug,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_host_list,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(patients_router)
app.include_router(station_router)

web_directory = Path(__file__).resolve().parent / "web"

app.mount(
    "/staff-dashboard/static",
    StaticFiles(directory=web_directory / "static"),
    name="staff-dashboard-static",
)


@app.get("/staff-dashboard", include_in_schema=False)
def staff_dashboard() -> FileResponse:
    return FileResponse(web_directory / "staff_dashboard.html")


@app.get("/")
def root() -> dict:
    return {"message": "QMMC PD1 Proof of Concept API"}


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "service": "qmmc-pd1-backend",
        "environment": settings.app_environment,
        "proof_of_concept": True,
        "pose_estimation": "not included",
        "deep_learning": "not included",
    }
