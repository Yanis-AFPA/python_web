from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import events, auth, users
from app.db.session import engine, AsyncSessionLocal
from app.db.base_class import Base
from app.db.init_db import init_db

# Create tables on startup (for prototype simplicity)
# In production, use Alembic
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Init DB (Seed Admin)
    async with AsyncSessionLocal() as session:
        await init_db(session)
        
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(events.router, prefix="/events", tags=["events"])

# Templates (Simple viewing)
templates = Jinja2Templates(directory="templates")

@app.get("/calendar")
async def calendar_page(request: Request):
    return templates.TemplateResponse("calendar.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("login.html", {"request": request}) # Redirect to login

