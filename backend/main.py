import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()


from backend.routers import auth, stores, questions, settings, employees, analytics
from backend.routers import reviews


@asynccontextmanager
async def lifespan(app: FastAPI):

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from db.database import init_db, close_db

    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="ReviewBot API",
    version="1.0.0",
    description="Web API для управления отзывами и вопросами на маркетплейсах",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/api/auth",       tags=["Auth"])
app.include_router(stores.router,     prefix="/api/stores",     tags=["Stores"])
app.include_router(reviews.router, prefix="/api/stores", tags=["Reviews"])
app.include_router(questions.router,  prefix="/api/stores",     tags=["Questions"])
app.include_router(settings.router,   prefix="/api/stores",     tags=["Settings"])
app.include_router(employees.router,  prefix="/api/employees",  tags=["Employees"])
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["Analytics"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
