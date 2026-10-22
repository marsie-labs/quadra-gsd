"""Composition root (RED stub): replaced by the real implementation in the GREEN commit."""

from fastapi import APIRouter, FastAPI

health_router = APIRouter()


def create_app() -> FastAPI:
    raise NotImplementedError
