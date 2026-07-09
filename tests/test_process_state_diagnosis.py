"""공정 상태 자동 진단 모듈 테스트."""
from __future__ import annotations

from src.spc.process_state_diagnosis import (
    DIAG_THRESHOLD_IDEAL,
    DIAG_THRESHOLD_PASS,
    STAGE_MACHINE,
    STAGE_PRELIMINARY,
    STAGE_PRODUCTION,
    classify_capability_index,
    diagnose_process_state,
    evaluate_cpk_ppk_ratio,
    evaluate_sample_adequacy,
    map_pipeline_stage_to_diag_stage,
    select_diagnosis_kpi,
)


def test_map_stage():
    assert map_pipeline_stage_to_diag_stage("mass_production") == STAGE_PRODUCTION
    assert map_pipeline_stage_to_diag_stage("development", machine_stages=("development",)) == STAGE_MACHINE
    assert map_pipeline_stage_to_diag_stage("pilot", machine_stages=()) == STAGE_PRELIMINARY


def test_select_kpi_production_valid_cpk():
    name, val = select_diagnosis_kpi(STAGE_PRODUCTION, cp_cpk_valid=True, cpk=1.4, ppk=1.5)
    assert name == "Cpk"
    assert val == 1.4


def test_select_kpi_preliminary_uses_ppk():
    name, val = select_diagnosis_kpi(STAGE_PRELIMINARY, cp_cpk_valid=False, cpk=1.4, ppk=1.8)
    assert name == "Ppk"
    assert val == 1.8


def test_classify_capability_production():
    level, sev = classify_capability_index(1.4, STAGE_PRODUCTION)
    assert sev == "ok"
    assert "합격" in level

    level2, sev2 = classify_capability_index(1.1, STAGE_PRODUCTION)
    assert sev2 == "warn"

    level3, sev3 = classify_capability_index(0.9, STAGE_PRODUCTION)
    assert sev3 == "bad"


def test_classify_capability_preliminary_stricter():
    level, sev = classify_capability_index(1.5, STAGE_PRELIMINARY)
    assert sev == "warn"  # below 1.67 ideal for PPAP


def test_cpk_ppk_ratio():
    ratio, verdict, sev = evaluate_cpk_ppk_ratio(1.2, 1.3)
    assert ratio is not None
    assert sev == "ok"

    _, _, sev2 = evaluate_cpk_ppk_ratio(0.8, 1.2)
    assert sev2 == "bad"


def test_sample_adequacy():
    _, sev = evaluate_sample_adequacy(125)
    assert sev == "ok"
    _, sev2 = evaluate_sample_adequacy(50)
    assert sev2 == "warn"


def test_diagnose_stable_capable_production():
    d = diagnose_process_state(
        cp=1.5,
        cpk=1.45,
        pp=1.48,
        ppk=1.42,
        n=125,
        subgroup_size=5,
        is_normal=True,
        is_stable=True,
        cp_cpk_valid=True,
        pipeline_stage="mass_production",
    )
    assert d.overall_severity == "ok"
    assert d.primary_kpi == "Cpk"
    assert d.pass_threshold == DIAG_THRESHOLD_PASS


def test_diagnose_unstable_bad():
    d = diagnose_process_state(
        cp=1.5,
        cpk=1.4,
        pp=1.5,
        ppk=1.4,
        n=125,
        subgroup_size=5,
        is_normal=True,
        is_stable=False,
        cp_cpk_valid=True,
        pipeline_stage="mass_production",
        has_we_violations=True,
    )
    assert d.control_severity == "bad"
    assert d.overall_severity == "bad"


def test_diagnose_ppap_stage_threshold():
    d = diagnose_process_state(
        cp=1.5,
        cpk=1.5,
        pp=1.5,
        ppk=1.5,
        n=125,
        subgroup_size=5,
        is_normal=True,
        is_stable=True,
        cp_cpk_valid=True,
        pipeline_stage="pre_mass_production",
        machine_stages=("development", "pilot", "pre_mass_production"),
    )
    assert d.diag_stage == STAGE_MACHINE
    assert d.pass_threshold == DIAG_THRESHOLD_IDEAL
    assert d.primary_kpi == "Ppk"
