from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .schemas import ProjectCreate
from cryptography.fernet import Fernet

from .security import decrypt_secret, encrypt_secret, hash_password, token_digest, verify_password, verify_totp


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_type: Mapped[str] = mapped_column(String(32))
    repository: Mapped[str] = mapped_column(String(2048))
    branch: Mapped[str] = mapped_column(String(255), default="main")
    deploy_path: Mapped[str] = mapped_column(String(2048))
    health_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    retain_releases: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    commit_hash: Mapped[str] = mapped_column(String(64), default="")
    previous_release: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    release_path: Mapped[str] = mapped_column(String(2048))
    operator: Mapped[str] = mapped_column(String(128), default="cli")
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime] = mapped_column(DateTime)
    result: Mapped[str] = mapped_column(String(32))
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_pending: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(2048))
    status_code: Mapped[int] = mapped_column(Integer)
    client_ip: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Store:
    def __init__(self, database_url: str, encryption_key: bytes | None = None) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        self.encryption_key = encryption_key or Fernet.generate_key()
        Base.metadata.create_all(self.engine)

    def create_project(self, payload: ProjectCreate) -> Project:
        with Session(self.engine) as session:
            project = Project(**payload.model_dump())
            session.add(project)
            session.commit()
            session.refresh(project)
            session.expunge(project)
            return project

    def projects(self) -> list[Project]:
        with Session(self.engine) as session:
            projects = list(session.scalars(select(Project).order_by(Project.name)))
            for project in projects:
                session.expunge(project)
            return projects

    def project(self, code: str) -> Project | None:
        with Session(self.engine) as session:
            project = session.scalar(select(Project).where(Project.code == code))
            if project is not None:
                session.expunge(project)
            return project

    def record_deployment(self, **values: object) -> Deployment:
        with Session(self.engine) as session:
            deployment = Deployment(**values)
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
            session.expunge(deployment)
            return deployment

    def deployments(self, project_id: int) -> list[Deployment]:
        with Session(self.engine) as session:
            query = select(Deployment).where(Deployment.project_id == project_id).order_by(Deployment.id.desc())
            deployments = list(session.scalars(query))
            for deployment in deployments:
                session.expunge(deployment)
            return deployments

    def recent_deployments(self, limit: int = 20) -> list[Deployment]:
        with Session(self.engine) as session:
            deployments = list(session.scalars(select(Deployment).order_by(Deployment.id.desc()).limit(limit)))
            for deployment in deployments:
                session.expunge(deployment)
            return deployments

    def set_password(self, username: str, password: str) -> None:
        if len(password) < 12:
            raise ValueError("password must be at least 12 characters")
        with Session(self.engine) as session:
            user = session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(username=username, password_hash=hash_password(password))
                session.add(user)
            else:
                user.password_hash = hash_password(password)
            session.execute(delete(LoginSession).where(LoginSession.user_id == user.id)) if user.id else None
            session.commit()

    def authenticate(self, username: str, password: str, totp: str | None = None) -> User | None:
        with Session(self.engine) as session:
            user = session.scalar(select(User).where(User.username == username, User.active.is_(True)))
            if user is None or not verify_password(password, user.password_hash):
                return None
            if user.totp_secret and (totp is None or not verify_totp(decrypt_secret(user.totp_secret, self.encryption_key), totp)):
                return None
            session.expunge(user)
            return user

    def create_session(self, user_id: int, lifetime_hours: int = 12) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=lifetime_hours)
        with Session(self.engine) as session:
            session.add(LoginSession(user_id=user_id, token_hash=token_digest(token), expires_at=expires_at))
            session.commit()
        return token, expires_at.replace(tzinfo=timezone.utc)

    def valid_session(self, token: str) -> bool:
        return self.session_user(token) is not None

    def session_user(self, token: str) -> int | None:
        with Session(self.engine) as session:
            query = select(LoginSession.user_id).where(
                LoginSession.token_hash == token_digest(token), LoginSession.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
            )
            return session.scalar(query)

    def begin_totp(self, user_id: int, secret: str) -> None:
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError("user does not exist")
            user.totp_pending = encrypt_secret(secret, self.encryption_key)
            session.commit()

    def enable_totp(self, user_id: int, code: str) -> None:
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            pending = decrypt_secret(user.totp_pending, self.encryption_key) if user and user.totp_pending else None
            if user is None or pending is None or not verify_totp(pending, code):
                raise ValueError("invalid TOTP code")
            user.totp_secret = user.totp_pending
            user.totp_pending = None
            session.commit()

    def record_audit(self, user_id: int | None, method: str, path: str, status_code: int, client_ip: str) -> None:
        with Session(self.engine) as session:
            session.add(
                AuditLog(user_id=user_id, method=method, path=path, status_code=status_code, client_ip=client_ip)
            )
            session.commit()

    def audit_logs(self, limit: int = 200) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
            return [
                {
                    "id": item.id,
                    "user_id": item.user_id,
                    "method": item.method,
                    "path": item.path,
                    "status_code": item.status_code,
                    "client_ip": item.client_ip,
                    "created_at": item.created_at,
                }
                for item in session.scalars(query)
            ]
