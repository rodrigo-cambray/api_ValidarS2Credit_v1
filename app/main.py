import os
import uuid
import hmac
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Date, DateTime, Integer, String, URL, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON
from starlette.exceptions import HTTPException as StarletteHTTPException


def database_url() -> str | URL:
    if value := os.getenv("DATABASE_URL"):
        return value
    return URL.create("mysql+pymysql", username=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                      host=os.getenv("MYSQL_HOST", "localhost"), port=int(os.getenv("MYSQL_PORT", "3306")),
                      database=os.getenv("MYSQL_DATABASE"))


engine_options = {"pool_pre_ping": True}
if str(database_url()).startswith("sqlite"):
    engine_options.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
engine = create_engine(database_url(), **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Oferta(Base):
    __tablename__ = "oferta"
    id_oferta: Mapped[int] = mapped_column(Integer, primary_key=True)
    fk_persona: Mapped[int] = mapped_column(BigInteger)
    etapa: Mapped[str] = mapped_column(String(30))


class PersonaBuro(Base):
    __tablename__ = "persona_buro"
    pk_buro: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_unykoo: Mapped[str | None] = mapped_column(String(55))
    id_calificador: Mapped[int | None] = mapped_column("idCalificador", Integer)
    fecha_consulta: Mapped[date | None] = mapped_column(Date)
    respuesta_buro: Mapped[str | None] = mapped_column(String(200))
    codigo_respuesta: Mapped[str | None] = mapped_column(String(45))
    bc_score: Mapped[str | None] = mapped_column(String(4))
    ingreso_mensual: Mapped[str | None] = mapped_column(String(45))
    fk_persona: Mapped[int] = mapped_column(BigInteger)
    respuesta_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    estatus: Mapped[str | None] = mapped_column(String(2))


class PersonaCirculo(Base):
    __tablename__ = "persona_circulo"
    id_persona_circulo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha_consulta: Mapped[datetime | None] = mapped_column(DateTime)
    fk_persona: Mapped[int] = mapped_column(BigInteger)
    respuesta_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    id_unykoo: Mapped[str | None] = mapped_column(String(50))
    estatus: Mapped[int | None] = mapped_column(Integer)


class PersonaQuash(Base):
    __tablename__ = "persona_quash"
    id_persona_quash: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha_consulta: Mapped[datetime | None] = mapped_column(DateTime)
    applicant_id: Mapped[str | None] = mapped_column(String(255))
    approval_score: Mapped[str | None] = mapped_column(String(15))
    rescue_segment: Mapped[str | None] = mapped_column(String(50))
    reglas: Mapped[str | None] = mapped_column(String(15))
    info_obs: Mapped[str | None] = mapped_column(String(50))
    label: Mapped[str | None] = mapped_column(String(10))
    estatus: Mapped[int | None] = mapped_column(Integer)
    fk_persona: Mapped[int] = mapped_column(BigInteger)
    edad_rule: Mapped[str | None] = mapped_column(String(20))
    score_rule: Mapped[str | None] = mapped_column(String(2))
    mops_rule: Mapped[str | None] = mapped_column(String(50))


class Estado(str, Enum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    PENDIENTE = "PENDIENTE"
    ERROR = "ERROR"


class Detalle(BaseModel):
    model_config = ConfigDict(extra="allow")
    reporteBuro: Any | None = None
    reporteCirculo: Any | None = None
    quash: Any | None = None
    idCalificador: int | None = None
    decision: Estado | None = None
    motivo: str | None = None


class AssessmentRequest(BaseModel):
    idOferta: int = Field(gt=0)
    calificadorDetalle: Detalle


class AssessmentResponse(BaseModel):
    assessmentId: str
    idOferta: int
    tipoCredito: str
    estado: Estado
    motivo: str | None
    idUnykoo: str | None
    reportesPersistidos: list[str]


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    traceId: str
    errors: list[dict[str, str]] | None = None


PROBLEM_OPENAPI = {
    "description": "RFC 9457 Problem Details",
    "content": {"application/problem+json": {"schema": ProblemDetails.model_json_schema()}},
}
bearer_scheme = HTTPBearer(auto_error=False)


def problem_response(request: Request, status_code: int, title: str, detail: str, code: str,
                     errors: list[dict[str, str]] | None = None,
                     headers: dict[str, str] | None = None) -> JSONResponse:
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    body: dict[str, Any] = {
        "type": f"https://credit-history-assessment-service/problems/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
        "traceId": trace_id,
    }
    if errors:
        body["errors"] = errors
    response_headers = {"X-Request-ID": trace_id}
    response_headers.update(headers or {})
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json", headers=response_headers)


def validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    problems = []
    for error in exc.errors():
        fields = [str(field).replace("~", "~0").replace("/", "~1") for field in error["loc"] if field != "body"]
        problems.append({"pointer": "#/" + "/".join(fields) if fields else "#", "detail": error["msg"]})
    return problems


def get_db():
    with SessionLocal() as session:
        yield session


def require_bearer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> None:
    secret = os.getenv("BEARER_TOKEN")
    if not secret:
        raise HTTPException(503, "Autenticación no configurada")
    if not credentials or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(credentials.credentials.encode(), secret.encode()):
        raise HTTPException(401, "Credenciales Bearer inválidas", headers={"WWW-Authenticate": "Bearer"})


def exists(value: Any) -> bool:
    return value not in (None, {}, [])


def first_value(value: Any, *keys: str) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) is not None:
                return value[key]
        for child in value.values():
            if (found := first_value(child, *keys)) is not None:
                return found
    if isinstance(value, list):
        for child in value:
            if (found := first_value(child, *keys)) is not None:
                return found
    return None


def decision(detail: Detalle) -> tuple[Estado, str | None]:
    # ponytail: pass-through until legacy rules are characterized and versioned.
    if detail.decision in (Estado.APROBADO, Estado.RECHAZADO):
        return detail.decision, detail.motivo
    return Estado.PENDIENTE, "DECISION_CALIFICADOR_AUSENTE"


def credit_type(offer: Oferta) -> str:
    return "SEGUNDO_CREDITO" if offer.etapa == "S2CREDIT" else "PRIMER_CREDITO"


def deactivate_reports(db: Session, person_id: int) -> None:
    db.execute(update(PersonaBuro).where(PersonaBuro.fk_persona == person_id, PersonaBuro.estatus == "1").values(estatus="0"))
    db.execute(update(PersonaCirculo).where(PersonaCirculo.fk_persona == person_id, PersonaCirculo.estatus == 1).values(estatus=0))
    db.execute(update(PersonaQuash).where(PersonaQuash.fk_persona == person_id, PersonaQuash.estatus == 1).values(estatus=0))


def persist_reports(db: Session, person_id: int, detail: Detalle) -> list[str]:
    now = datetime.now()
    saved: list[str] = []
    deactivate_reports(db, person_id)
    if exists(detail.reporteBuro):
        bureau = detail.reporteBuro
        db.add(PersonaBuro(id_unykoo=first_value(bureau, "id_unykoo", "idUnykoo"), id_calificador=detail.idCalificador,
               fecha_consulta=now.date(), respuesta_buro=first_value(bureau, "respuesta_buro", "respuestaBuro", "respuesta"),
               codigo_respuesta=first_value(bureau, "codigo_respuesta", "codigoRespuesta", "code"),
               bc_score=str(first_value(bureau, "bc_score", "bcScore", "score") or "") or None,
               ingreso_mensual=str(first_value(bureau, "ingreso_mensual", "ingresoMensual") or "") or None,
               fk_persona=person_id, respuesta_json=bureau, estatus="1"))
        saved.append("BURO")
    if exists(detail.reporteCirculo):
        circle = detail.reporteCirculo
        db.add(PersonaCirculo(fecha_consulta=now, fk_persona=person_id, respuesta_json=circle,
               id_unykoo=first_value(circle, "id_unykoo", "idUnykoo"), estatus=1))
        saved.append("CIRCULO")
    if exists(detail.quash):
        quash = detail.quash
        db.add(PersonaQuash(fecha_consulta=now, applicant_id=first_value(quash, "applicant_id", "applicantId"),
               approval_score=first_value(quash, "approval_score", "approvalScore"), rescue_segment=first_value(quash, "rescue_segment", "rescueSegment"),
               reglas=first_value(quash, "reglas", "rules"), info_obs=first_value(quash, "info_obs", "infoObs"),
               label=first_value(quash, "label"), estatus=1, fk_persona=person_id,
               edad_rule=first_value(quash, "edad_rule", "edadRule"), score_rule=first_value(quash, "score_rule", "scoreRule"),
               mops_rule=first_value(quash, "mops_rule", "mopsRule")))
        saved.append("QUASH")
    return saved


def assessment_response(offer: Oferta, state: Estado, reason: str | None, reports: list[str], id_unykoo: str | None) -> AssessmentResponse:
    return AssessmentResponse(assessmentId=f"oferta_{offer.id_oferta}", idOferta=offer.id_oferta,
                              tipoCredito=credit_type(offer), estado=state, motivo=reason,
                              idUnykoo=id_unykoo, reportesPersistidos=reports)


app = FastAPI(title="credit-history-assessment-service", version="1.0.0")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    titles = {400: ("Solicitud no válida", "BAD_REQUEST"), 404: ("Recurso no encontrado", "NOT_FOUND"),
              409: ("Conflicto", "CONFLICT"), 403: ("Acceso denegado", "FORBIDDEN"),
              401: ("No autorizado", "UNAUTHORIZED"), 503: ("Servicio no disponible", "AUTH_NOT_CONFIGURED")}
    title, code = titles.get(exc.status_code, ("Error de solicitud", "HTTP_ERROR"))
    return problem_response(request, exc.status_code, title, str(exc.detail), code, headers=dict(exc.headers or {}))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return problem_response(request, 422, "Solicitud no válida", "Revise los campos indicados.", "VALIDATION_ERROR",
                            validation_errors(exc))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return problem_response(request, 500, "Error interno", "No fue posible completar la solicitud.", "INTERNAL_ERROR")


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready", responses={401: PROBLEM_OPENAPI, 500: PROBLEM_OPENAPI, 503: PROBLEM_OPENAPI})
def ready(_: None = Depends(require_bearer), db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.post("/v1/credit-assessments", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED,
          responses={401: PROBLEM_OPENAPI, 404: PROBLEM_OPENAPI, 422: PROBLEM_OPENAPI, 500: PROBLEM_OPENAPI, 503: PROBLEM_OPENAPI})
def assess(request: AssessmentRequest, _: None = Depends(require_bearer), db: Session = Depends(get_db)):
    offer = db.get(Oferta, request.idOferta)
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")
    state, reason = decision(request.calificadorDetalle)
    reports: list[str] = []
    try:
        if credit_type(offer) == "PRIMER_CREDITO":
            reports = persist_reports(db, offer.fk_persona, request.calificadorDetalle)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return assessment_response(offer, state, reason, reports,
                               first_value(request.calificadorDetalle.reporteCirculo, "id_unykoo", "idUnykoo"))


@app.get("/v1/credit-assessments/by-oferta/{idOferta}", response_model=AssessmentResponse,
         responses={401: PROBLEM_OPENAPI, 404: PROBLEM_OPENAPI, 422: PROBLEM_OPENAPI, 500: PROBLEM_OPENAPI, 503: PROBLEM_OPENAPI})
def by_offer(idOferta: int, _: None = Depends(require_bearer), db: Session = Depends(get_db)):
    offer = db.get(Oferta, idOferta)
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")
    person_id = offer.fk_persona
    reports = []
    if db.scalar(select(PersonaBuro.pk_buro).where(PersonaBuro.fk_persona == person_id, PersonaBuro.estatus == "1").limit(1)):
        reports.append("BURO")
    circle = db.scalar(select(PersonaCirculo).where(PersonaCirculo.fk_persona == person_id, PersonaCirculo.estatus == 1).limit(1))
    if circle:
        reports.append("CIRCULO")
    if db.scalar(select(PersonaQuash.id_persona_quash).where(PersonaQuash.fk_persona == person_id, PersonaQuash.estatus == 1).limit(1)):
        reports.append("QUASH")
    return assessment_response(offer, Estado.PENDIENTE, "DECISION_NO_PERSISTIDA", reports, circle.id_unykoo if circle else None)
