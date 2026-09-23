import hmac
import os
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Integer, String, URL, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
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
    fk_persona: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    etapa: Mapped[str] = mapped_column(String(30))


class S2AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idOferta: int = Field(gt=0)


class S2AssessmentResponse(BaseModel):
    idOferta: int
    etapa: str
    mensaje: str
    estatus: str | None


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    traceId: str
    estatus: str | None = None
    errors: list[dict[str, str]] | None = None


PROBLEM_OPENAPI = {"description": "RFC 9457 Problem Details",
                   "content": {"application/problem+json": {"schema": ProblemDetails.model_json_schema()}}}
bearer_scheme = HTTPBearer(auto_error=False)


def problem_response(request: Request, status_code: int, title: str, detail: str, code: str,
                     errors: list[dict[str, str]] | None = None,
                     headers: dict[str, str] | None = None) -> JSONResponse:
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    body: dict[str, Any] = {"type": f"https://credit-history-assessment-service/problems/{code.lower().replace('_', '-')}",
                            "title": title, "status": status_code, "detail": detail, "instance": request.url.path,
                            "code": code, "traceId": trace_id, "estatus": None}
    if errors:
        body["errors"] = errors
    response_headers = {"X-Request-ID": trace_id}
    response_headers.update(headers or {})
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json", headers=response_headers)


def validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    return [{"pointer": "#/" + "/".join(str(field) for field in error["loc"] if field != "body"),
             "detail": error["msg"]} for error in exc.errors()]


def get_db():
    with SessionLocal() as session:
        yield session


def require_bearer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> None:
    secret = os.getenv("BEARER_TOKEN")
    if not secret:
        raise HTTPException(503, "Autenticación no configurada")
    if not credentials or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(credentials.credentials.encode(), secret.encode()):
        raise HTTPException(401, "Credenciales Bearer inválidas", headers={"WWW-Authenticate": "Bearer"})


def valid_person_id(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


app = FastAPI(title="credit-history-assessment-service", version="3.0.0")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    titles = {400: ("Solicitud no válida", "BAD_REQUEST"), 401: ("No autorizado", "UNAUTHORIZED"),
              403: ("Acceso denegado", "FORBIDDEN"), 404: ("Recurso no encontrado", "NOT_FOUND"),
              503: ("Servicio no disponible", "AUTH_NOT_CONFIGURED")}
    title, code = titles.get(exc.status_code, ("Error de solicitud", "HTTP_ERROR"))
    return problem_response(request, exc.status_code, title, str(exc.detail), code, headers=dict(exc.headers or {}))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return problem_response(request, 422, "Solicitud no válida", "Revise los campos indicados.", "VALIDATION_ERROR", validation_errors(exc))


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


@app.post("/v1/s2-credit-assessments", response_model=S2AssessmentResponse, status_code=status.HTTP_200_OK,
          responses={401: PROBLEM_OPENAPI, 404: PROBLEM_OPENAPI, 422: PROBLEM_OPENAPI, 500: PROBLEM_OPENAPI,
                     503: PROBLEM_OPENAPI})
def assess_s2(request: S2AssessmentRequest, _: None = Depends(require_bearer), db: Session = Depends(get_db)):
    offer = db.get(Oferta, request.idOferta)
    if not offer:
        raise HTTPException(404, "La oferta no ha sido originada.")
    if offer.etapa == "S2CREDIT":
        return S2AssessmentResponse(idOferta=offer.id_oferta, etapa=offer.etapa,
                                    mensaje="La oferta ya está en etapa S2Credit. Operación no válida.", estatus=None)
    person_id = valid_person_id(offer.fk_persona)
    if person_id is None:
        raise HTTPException(404, "La oferta no tiene un prospecto asignado aún.")

    other_stages = db.scalars(select(Oferta.etapa).where(Oferta.fk_persona == person_id,
                                                          Oferta.id_oferta != offer.id_oferta)).all()
    if "S2CREDIT" in other_stages:
        message = "El prospecto ya tiene un crédito pagado anteriormente."
        assessment_status = "SegundoCredito"
    elif other_stages:
        message = "El prospecto no tiene una oferta en S2Credit."
        assessment_status = "PrimerCredito"
    else:
        message = "El prospecto no tiene solicitudes de crédito anteriores a esta."
        assessment_status = "PrimerCredito"
    return S2AssessmentResponse(idOferta=offer.id_oferta, etapa=offer.etapa, mensaje=message, estatus=assessment_status)
