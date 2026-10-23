"""Service container. The app lifespan sets ``services``; tests inject their own."""

from dataclasses import dataclass

from app.realtime.hub import RealtimeHub
from app.services.sessions import SessionService


@dataclass
class Services:
    sessions: SessionService
    hub: RealtimeHub


services: Services | None = None


def get_services() -> Services:
    if services is None:
        raise RuntimeError("services not initialised")
    return services
