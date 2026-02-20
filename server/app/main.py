from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api.v1.router import api_router
from app.core.config import Settings

settings = Settings()

# server/app/main.py → server/app → server → project_root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

app = FastAPI(
    title="MLCC 계측기 데이터 수집 서버",
    version="2.0.0",
    description="MLCC 특성 계측 데이터 수집 및 대시보드 API 서버",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 및 Jinja2 템플릿 마운트
_static_dir = _PROJECT_ROOT / "web" / "static"
_templates_dir = _PROJECT_ROOT / "web" / "templates"

app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
_templates = Jinja2Templates(directory=str(_templates_dir))

app.include_router(api_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """MLCC 계측 대시보드 웹 페이지"""
    return _templates.TemplateResponse("dashboard/index.html", {"request": request})
