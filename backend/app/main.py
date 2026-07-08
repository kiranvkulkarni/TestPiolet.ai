from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import (
    agent,
    auth,
    comments,
    dashboard,
    device_models,
    files,
    leaves,
    notifications,
    projects,
    tasks,
    test_cycles,
    test_requests,
    users,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="QA Task Assigner", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(device_models.router)
app.include_router(projects.router)
app.include_router(test_cycles.router)
app.include_router(test_requests.router)
app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(files.router)
app.include_router(leaves.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(agent.router)


@app.get("/health")
def health():
    return {"status": "ok"}
