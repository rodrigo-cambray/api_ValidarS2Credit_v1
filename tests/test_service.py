import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["BEARER_TOKEN"] = "test-token"

from fastapi.testclient import TestClient
from app import main

client = TestClient(main.app)
AUTH = {"Authorization": "Bearer test-token"}


def reset_db():
    main.Base.metadata.drop_all(main.engine)
    main.Base.metadata.create_all(main.engine)


def add_offer(id_oferta: int, fk_persona: object, etapa: str = "PRECALIFICADA"):
    with main.SessionLocal.begin() as db:
        db.add(main.Oferta(id_oferta=id_oferta, fk_persona=fk_persona, etapa=etapa))


def assess(id_oferta: int):
    return client.post("/v1/s2-credit-assessments", json={"idOferta": id_oferta}, headers=AUTH)


def test_offer_not_originated_returns_problem_details():
    reset_db()
    result = assess(99)
    assert result.status_code == 404
    assert result.headers["content-type"].startswith("application/problem+json")
    assert result.json()["detail"] == "La oferta no ha sido originada."
    assert result.json()["estatus"] is None


def test_invalid_person_id_returns_prospect_not_assigned():
    for index, value in enumerate((None, 0, -1, "invalido"), start=1):
        reset_db()
        add_offer(index, value)
        result = assess(index)
        assert result.status_code == 404
        assert result.json()["detail"] == "La oferta no tiene un prospecto asignado aún."
        assert result.json()["estatus"] is None


def test_other_s2credit_offer_has_priority():
    reset_db()
    add_offer(10, 50)
    add_offer(11, 50, "S2CREDIT")
    result = assess(10)
    assert result.status_code == 200
    assert result.json() == {"idOferta": 10, "etapa": "PRECALIFICADA", "mensaje": "El prospecto ya tiene un crédito pagado anteriormente.",
                             "estatus": "SegundoCredito"}


def test_other_offers_without_s2credit_are_reported():
    reset_db()
    add_offer(20, 60)
    add_offer(21, 60, "RECHAZADA")
    result = assess(20)
    assert result.status_code == 200
    assert result.json()["mensaje"] == "El prospecto no tiene una oferta en S2Credit."
    assert result.json()["etapa"] == "PRECALIFICADA"
    assert result.json()["estatus"] == "PrimerCredito"


def test_current_s2credit_offer_is_not_a_valid_operation():
    reset_db()
    add_offer(30, 70, "S2CREDIT")
    result = assess(30)
    assert result.status_code == 200
    assert result.json() == {"idOferta": 30, "etapa": "S2CREDIT", "mensaje": "La oferta ya está en etapa S2Credit. Operación no válida.",
                             "estatus": None}


def test_offer_without_prior_requests_is_first_credit():
    reset_db()
    add_offer(31, 71)
    result = assess(31)
    assert result.status_code == 200
    assert result.json()["mensaje"] == "El prospecto no tiene solicitudes de crédito anteriores a esta."
    assert result.json()["estatus"] == "PrimerCredito"


def test_s2_assessment_validates_input_and_is_bearer_protected(monkeypatch):
    reset_db()
    add_offer(40, 80)
    for headers in ({}, {"Authorization": "Bearer incorrecto"}):
        assert client.get("/health/ready", headers=headers).status_code == 401
        error = client.post("/v1/s2-credit-assessments", json={"idOferta": 40}, headers=headers)
        assert error.status_code == 401
        assert error.json()["estatus"] is None
    invalid = client.post("/v1/s2-credit-assessments", json={"idOferta": 0, "decision": "APROBADO"}, headers=AUTH)
    assert invalid.status_code == 422
    assert invalid.headers["content-type"].startswith("application/problem+json")
    assert invalid.json()["code"] == "VALIDATION_ERROR"
    assert invalid.json()["estatus"] is None
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready", headers=AUTH).status_code == 200
    openapi = main.app.openapi()
    assert openapi["info"]["version"] == "3.0.0"
    assert openapi["components"]["securitySchemes"]["HTTPBearer"] == {"type": "http", "scheme": "bearer"}
    assert set(openapi["paths"]) == {"/health/live", "/health/ready", "/v1/s2-credit-assessments"}
    monkeypatch.delenv("BEARER_TOKEN")
    unavailable = client.get("/health/ready", headers=AUTH)
    assert unavailable.status_code == 503
    assert unavailable.json()["estatus"] is None


def test_service_has_only_offer_read_model_and_no_report_dependencies():
    source = Path(main.__file__).read_text(encoding="utf-8")
    for forbidden in ("PersonaBuro", "PersonaCirculo", "PersonaQuash", "persona_buro", "persona_circulo", "persona_quash"):
        assert forbidden not in source
    assert set(main.Base.metadata.tables) == {"oferta"}
