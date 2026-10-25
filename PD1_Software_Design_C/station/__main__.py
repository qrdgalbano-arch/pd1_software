import uvicorn

from station.config import get_settings

settings = get_settings()
uvicorn.run("station.server:app", host=settings.station_host, port=settings.station_port, log_level="info")
