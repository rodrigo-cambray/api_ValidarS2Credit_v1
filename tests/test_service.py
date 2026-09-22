import os

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from app.main import Base, Oferta, PersonaBuro, PersonaCirculo, PersonaQuash, SessionLocal, app, engine

client = TestClient(app)


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
    result = client.post("/v1/credit-assessments", json=payload)
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
        db.add(Oferta(id_oferta=11, fk_persona=100, etapa="S2CREADIT"))
    result = client.post("/v1/credit-assessments", json={"idOferta": 11, "calificadorDetalle": {
        "decision": "RECHAZADO", "motivo": "POLITICA_S2", "reporteBuro": {"score": 700}}})
    assert result.status_code == 201
    assert result.json()["tipoCredito"] == "SEGUNDO_CREDITO"
    assert result.json()["estado"] == "RECHAZADO"
    assert result.json()["reportesPersistidos"] == []
    with SessionLocal() as db:
        assert db.query(PersonaBuro).count() == 0
