"""Testes das migrations F2.2."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.api.db.migrations import run_migrations
from backend.api.db.models import (
    AppConfigRecord,
    CaseRecord,
    ExecutionRecord,
    LineTypeRecord,
)


def test_migrations_cria_tabelas_novas(tmp_path: Path) -> None:
    """Em DB vazio, migrations criam cases, executions e app_config."""
    db = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db}")
    created = run_migrations(engine)
    assert "cases" in created
    assert "executions" in created
    assert "app_config" in created
    # line_types é criada também porque o model está registrado no Base
    assert "line_types" in created


def test_migrations_idempotente(tmp_path: Path) -> None:
    """Rodar migrations duas vezes não recria tabelas."""
    db = tmp_path / "twice.db"
    engine = create_engine(f"sqlite:///{db}")
    run_migrations(engine)
    second = run_migrations(engine)
    assert second == []


def test_cases_aceita_insert_valido(tmp_db: Path) -> None:
    """CaseRecord com todos os campos aceita inserção."""
    from backend.api.db import session as ds
    with ds.SessionLocal() as db:
        rec = CaseRecord(
            name="Caso de teste",
            description="BC-01 like",
            input_json="{}",
            mode="Tension",
            water_depth=300.0,
            line_length=450.0,
            criteria_profile="MVP_Preliminary",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        assert rec.id is not None
        assert rec.created_at is not None


def test_cases_rejeita_name_vazio(tmp_db: Path) -> None:
    """CheckConstraint name NOT EMPTY funciona."""
    from backend.api.db import session as ds
    from sqlalchemy.exc import IntegrityError
    with ds.SessionLocal() as db:
        rec = CaseRecord(
            name="",
            input_json="{}",
            mode="Tension",
            water_depth=300.0,
            line_length=450.0,
        )
        db.add(rec)
        try:
            db.commit()
            assert False, "deveria ter falhado com name vazio"
        except IntegrityError:
            db.rollback()


def test_cascade_deleta_executions(tmp_db: Path) -> None:
    """DELETE em CaseRecord remove ExecutionRecord via cascade."""
    from backend.api.db import session as ds
    with ds.SessionLocal() as db:
        case = CaseRecord(
            name="c1", input_json="{}",
            mode="Tension", water_depth=300.0, line_length=450.0,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        db.add_all([
            ExecutionRecord(
                case_id=case.id, result_json="{}", status="converged",
                alert_level="ok", fairlead_tension=100.0,
            ),
            ExecutionRecord(
                case_id=case.id, result_json="{}", status="converged",
                alert_level="ok", fairlead_tension=110.0,
            ),
        ])
        db.commit()
        assert db.query(ExecutionRecord).count() == 2
        db.delete(case)
        db.commit()
        assert db.query(ExecutionRecord).count() == 0


def test_app_config_chave_unica(tmp_db: Path) -> None:
    """AppConfigRecord.key é PK — inserções duplicadas falham."""
    from backend.api.db import session as ds
    from sqlalchemy.exc import IntegrityError
    with ds.SessionLocal() as db:
        db.add(AppConfigRecord(key="lang", value="pt-BR"))
        db.commit()
        db.add(AppConfigRecord(key="lang", value="en-US"))
        try:
            db.commit()
            assert False, "PK duplicada deveria falhar"
        except IntegrityError:
            db.rollback()


def test_line_type_record_reflete_schema_existente(tmp_db: Path) -> None:
    """
    LineTypeRecord consegue inserir com os mesmos campos do seed_catalog.
    Smoke test garantindo que o ORM descreve corretamente a tabela.
    """
    from backend.api.db import session as ds
    with ds.SessionLocal() as db:
        rec = LineTypeRecord(
            legacy_id=1, line_type="IWRCEIPS", category="Wire",
            base_unit_system="imperial",
            diameter=0.0254, dry_weight=27.0, wet_weight=22.4,
            break_strength=459_946.0, modulus=6.76e10,
            qmoor_ea=3.42e7, gmoor_ea=4.96e7,
            seabed_friction_cf=0.6, data_source="legacy_qmoor",
        )
        db.add(rec)
        db.commit()
        assert rec.id is not None
