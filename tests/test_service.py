import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["BEARER_TOKEN"] = "test-token"

from fastapi.testclient import TestClient
from app.main import Base, Oferta, PersonaBuro, PersonaCirculo, PersonaQuash, SessionLocal, app, engine

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-token"}


def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_first_credit_writes_legacy_reports_and_deactivates_previous_ones():
    reset_db()
    with SessionLocal.begin() as db:
        db.add(Oferta(id_oferta=10, fk_persona=99, etapa="PRECALIFICADA"))
        db.add(PersonaBuro(fk_persona=99, estatus="1"))
    payload = {"idOferta": 10, "calificadorDetalle": {
        "idCalificador": 5, "decision": "APROBADO",
        "reporteBuro": {"score": 720, "ingresoMensual": 10000},
        "reporteCirculo": {"idUnykoo": "u-1"},
        "quash": {"applicantId": "q-1", "approvalScore": "800"}}}
    result = client.post("/v1/credit-assessments", json=payload, headers=AUTH)
    assert result.status_code == 201
    assert result.json()["assessmentId"] == "oferta_10"
    assert result.json()["reportesPersistidos"] == ["BURO", "CIRCULO", "QUASH"]
    with SessionLocal() as db:
        assert db.query(PersonaBuro).count() == 2
        assert db.query(PersonaBuro.estatus).filter(PersonaBuro.pk_buro == 1).scalar() == "0"
        assert db.query(PersonaCirculo.id_unykoo).scalar() == "u-1"
        assert db.query(PersonaQuash.applicant_id).scalar() == "q-1"


def test_second_credit_does_not_write_reports():
    reset_db()
    with SessionLocal.begin() as db:
        db.add(Oferta(id_oferta=11, fk_persona=100, etapa="S2CREDIT"))
    result = client.post("/v1/credit-assessments", json={"idOferta": 11, "calificadorDetalle": {
        "decision": "RECHAZADO", "motivo": "POLITICA_S2", "reporteBuro": {"score": 700}}}, headers=AUTH)
    assert result.status_code == 201
    assert result.json()["tipoCredito"] == "SEGUNDO_CREDITO"
    assert result.json()["estado"] == "RECHAZADO"
    assert result.json()["reportesPersistidos"] == []
    with SessionLocal() as db:
        assert db.query(PersonaBuro).count() == 0


def test_errors_use_rfc_9457_problem_details():
    reset_db()
    result = client.post("/v1/credit-assessments", json={"idOferta": 0, "calificadorDetalle": {}}, headers=AUTH)
    assert result.status_code == 422
    assert result.headers["content-type"].startswith("application/problem+json")
    body = result.json()
    assert body["status"] == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"][0]["pointer"] == "#/idOferta"


def test_bearer_protects_database_endpoints_and_is_published(monkeypatch):
    reset_db()
    with SessionLocal.begin() as db:
        db.add(Oferta(id_oferta=12, fk_persona=101, etapa="PRECALIFICADA"))
    payload = {"idOferta": 12, "calificadorDetalle": {"decision": "APROBADO"}}
    for headers in ({}, {"Authorization": "Bearer incorrecto"}):
        assert client.get("/health/ready", headers=headers).status_code == 401
        assert client.post("/v1/credit-assessments", json=payload, headers=headers).status_code == 401
        assert client.get("/v1/credit-assessments/by-oferta/12", headers=headers).status_code == 401
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready", headers=AUTH).status_code == 200
    assert client.post("/v1/credit-assessments", json=payload, headers=AUTH).status_code == 201
    assert client.get("/v1/credit-assessments/by-oferta/12", headers=AUTH).status_code == 200
    assert app.openapi()["components"]["securitySchemes"]["HTTPBearer"] == {"type": "http", "scheme": "bearer"}
    monkeypatch.delenv("BEARER_TOKEN")
    assert client.get("/health/ready", headers=AUTH).status_code == 503
