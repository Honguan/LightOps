from __future__ import annotations

import platform
import tarfile
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from . import __version__
from .backups import BackupService
from .config import load_settings
from .deployments import DeploymentService
from .insights import daily_report, disk_alerts, process_rankings, ssh_failures
from .history import load_today
from .monitoring import system_snapshot
from .operations import Operations
from .schemas import BackupCreate, BackupRestore, LoginRequest, ProjectCreate, ProjectView, TotpEnable
from .security import LoginRateLimiter, new_totp_secret
from .scheduler import build_scheduler
from .store import Store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = load_settings()
    scheduler = None if settings.scheduler_disabled else build_scheduler(settings)
    if scheduler is not None:
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="LightOps", version=__version__, lifespan=lifespan)
login_limiter = LoginRateLimiter()


@app.middleware("http")
async def authenticate_api(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    settings = load_settings()
    client_ip = request.client.host if request.client else "unknown"
    if settings.ip_allowlist and client_ip not in settings.ip_allowlist:
        return JSONResponse(status_code=403, content={"detail": "client IP is not allowed"})
    provider = request.app.dependency_overrides.get(get_store, get_store)
    store = getattr(request.app.state, "auth_store", None)
    user_id = None
    protected = path not in {"/api/health", "/api/auth/login"}
    if protected and not settings.auth_disabled:
        store = store or provider()
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "authentication required"})
        user_id = store.session_user(authorization[7:])
        if user_id is None:
            return JSONResponse(status_code=401, content={"detail": "session is invalid or expired"})
        request.state.user_id = user_id
    response = await call_next(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        store = store or provider()
        store.record_audit(user_id, request.method, path, response.status_code, client_ip)
    return response


def get_operations() -> Operations:
    settings = load_settings()
    return Operations(
        settings.manifests_dir,
        privileged=platform.system() == "Linux",
        additional_services=settings.custom_services,
    )


def get_store() -> Store:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    key = settings.secret_key_file.read_bytes().strip() if settings.secret_key_file.is_file() else None
    return Store(settings.database_url, key)


def get_backup_service() -> BackupService:
    settings = load_settings()
    return BackupService(settings.backup_dir, settings.backup_retention)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, store: Store = Depends(get_store)) -> dict[str, str]:
    address = request.client.host if request.client else "unknown"
    if not login_limiter.allowed(address):
        raise HTTPException(status_code=429, detail="too many login attempts")
    user = store.authenticate(payload.username, payload.password, payload.totp)
    if user is None:
        login_limiter.failed(address)
        raise HTTPException(status_code=401, detail="invalid username or password")
    login_limiter.succeeded(address)
    token, expires_at = store.create_session(user.id)
    return {"token": token, "expires_at": expires_at.isoformat()}


@app.post("/api/auth/totp/setup")
def setup_totp(request: Request, store: Store = Depends(get_store)) -> dict[str, str]:
    secret = new_totp_secret()
    store.begin_totp(request.state.user_id, secret)
    return {"secret": secret, "uri": f"otpauth://totp/LightOps:admin?secret={secret}&issuer=LightOps"}


@app.post("/api/auth/totp/enable")
def enable_totp(payload: TotpEnable, request: Request, store: Store = Depends(get_store)) -> dict[str, str]:
    try:
        store.enable_totp(request.state.user_id, payload.code)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"status": "enabled"}


def get_deployment_service(store: Store = Depends(get_store)) -> DeploymentService:
    return DeploymentService(store)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/system")
def system() -> dict[str, object]:
    return system_snapshot()


@app.get("/api/services")
def services(operations: Operations = Depends(get_operations)) -> list[dict[str, object]]:
    return operations.service_statuses()


@app.post("/api/services/{name}/{action}")
def service_action(name: str, action: str, operations: Operations = Depends(get_operations)) -> dict[str, str]:
    try:
        return operations.service_action(name, action)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/apps")
def apps(operations: Operations = Depends(get_operations)) -> list[dict[str, object]]:
    return operations.manifests()


@app.post("/api/apps/{name}/{action}")
def app_action(name: str, action: str, operations: Operations = Depends(get_operations)) -> dict[str, object]:
    try:
        return operations.app_action(name, action)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown app: {name}") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/apps/{name}/logs")
def app_logs(name: str, operations: Operations = Depends(get_operations)) -> list[dict[str, str]]:
    try:
        return operations.app_logs(name)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown app: {name}") from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/stacks/{name}/install")
def install_stack(name: str, operations: Operations = Depends(get_operations)) -> dict[str, object]:
    try:
        return operations.stack_install(name)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown stack: {name}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/docker/containers")
def docker_containers(operations: Operations = Depends(get_operations)) -> list[dict[str, object]]:
    return operations.containers()


@app.post("/api/docker/containers/{container_id}/{action}")
def docker_action(container_id: str, action: str, operations: Operations = Depends(get_operations)) -> dict[str, str]:
    try:
        return operations.container_action(container_id, action)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/docker/containers/{container_id}/logs")
def docker_logs(container_id: str, operations: Operations = Depends(get_operations)) -> dict[str, str]:
    try:
        return operations.container_logs(container_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/projects", response_model=list[ProjectView])
def projects(store: Store = Depends(get_store)) -> list[object]:
    return store.projects()


@app.post("/api/projects", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, store: Store = Depends(get_store)) -> object:
    try:
        return store.create_project(payload)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail=f"project code already exists: {payload.code}") from error


@app.get("/api/backups")
def backups(service: BackupService = Depends(get_backup_service)) -> list[dict[str, object]]:
    return service.list()


@app.post("/api/backups", status_code=status.HTTP_201_CREATED)
def create_backup(payload: BackupCreate, service: BackupService = Depends(get_backup_service)) -> dict[str, object]:
    try:
        return service.create(payload.name, payload.sources)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/backups/{filename}/restore")
def restore_backup(filename: str, payload: BackupRestore, service: BackupService = Depends(get_backup_service)) -> dict[str, str]:
    try:
        return service.restore(filename, Path(payload.target))
    except (OSError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/projects/{code}/deploy")
def deploy_project(code: str, service: DeploymentService = Depends(get_deployment_service)) -> dict[str, object]:
    try:
        return service.deploy(code)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown project: {code}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/projects/{code}/rollback")
def rollback_project(code: str, service: DeploymentService = Depends(get_deployment_service)) -> dict[str, object]:
    try:
        return service.rollback(code)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown project: {code}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/projects/{code}/deployments")
def project_deployments(code: str, service: DeploymentService = Depends(get_deployment_service)) -> list[dict[str, object]]:
    try:
        return service.history(code)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown project: {code}") from error


@app.get("/api/processes")
def processes() -> dict[str, list[dict[str, object]]]:
    return process_rankings()


@app.get("/api/security/ssh-failures")
def security_ssh_failures() -> list[dict[str, str]]:
    return ssh_failures()


@app.get("/api/alerts")
def alerts() -> list[dict[str, object]]:
    return disk_alerts(system_snapshot())


@app.get("/api/reports/daily")
def report_daily(
    operations: Operations = Depends(get_operations),
    backup_service: BackupService = Depends(get_backup_service),
    store: Store = Depends(get_store),
) -> dict[str, object]:
    snapshot = system_snapshot()
    failures = ssh_failures()
    rankings = process_rankings()
    abnormal = [item for item in rankings["by_cpu"] if item["cpu_percent"] >= 80]
    abnormal.extend(item for item in rankings["by_memory"] if item["memory_percent"] >= 50 and item not in abnormal)
    services = operations.service_statuses()
    containers = operations.containers()
    deployments = store.recent_deployments()
    return daily_report(
        snapshot,
        disk_alerts(snapshot),
        failures,
        load_today(load_settings().data_dir),
        abnormal_processes=abnormal,
        service_stops=[item for item in services if not item["active"]],
        docker_anomalies=[item for item in containers if not str(item["status"]).lower().startswith("up")],
        backup_results=backup_service.list()[:20],
        deployment_results=[
            {"project_id": item.project_id, "result": item.result, "finished_at": item.finished_at.isoformat()}
            for item in deployments
        ],
    )


@app.get("/api/audit-logs")
def audit_logs(store: Store = Depends(get_store)) -> list[dict[str, object]]:
    return store.audit_logs()


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


def run() -> None:
    uvicorn.run("lightops.api:app", host="127.0.0.1", port=9080)
