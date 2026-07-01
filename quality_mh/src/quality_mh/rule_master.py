"""업무 마스터(rule master) 데이터 및 조회 함수."""
from __future__ import annotations

from copy import deepcopy

from quality_mh.models import FrequencyMethod, RoundingPolicy, RuleMaster, TaskType

WG_LIST = ("입고", "공정", "완성", "시험", "공통")

_DEFAULT_RULES: list[RuleMaster] = [
    # ── 입고 ──
    RuleMaster(
        task_code="IN-001",
        wg="입고",
        task_name="정기 점검",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="IN-002",
        wg="입고",
        task_name="정기 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="IN-003",
        wg="입고",
        task_name="외주품 입고검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="IN-004",
        wg="입고",
        task_name="4M/EO 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="IN-005",
        wg="입고",
        task_name="검사기준/대상 변경",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    # ── 공정 ──
    RuleMaster(
        task_code="PR-001",
        wg="공정",
        task_name="초중종 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="PR-002",
        wg="공정",
        task_name="순회 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="PR-003",
        wg="공정",
        task_name="라인 AUDIT",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="PR-004",
        wg="공정",
        task_name="변경시점 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="PR-005",
        wg="공정",
        task_name="공정 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="PR-006",
        wg="공정",
        task_name="정밀 측정(반제품)",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="PR-007",
        wg="공정",
        task_name="공정 검사기준 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    # ── 완성 ──
    RuleMaster(
        task_code="FN-001",
        wg="완성",
        task_name="정밀 측정(완성품)",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="FN-002",
        wg="완성",
        task_name="성능 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="FI-001",
        wg="완성",
        task_name="최종 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="FN-003",
        wg="완성",
        task_name="완성품 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="FN-004",
        wg="완성",
        task_name="장기재고 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="FN-005",
        wg="완성",
        task_name="상품류 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="FN-006",
        wg="완성",
        task_name="CKD/KD 검사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    # ── 시험 ──
    RuleMaster(
        task_code="TM-001",
        wg="시험",
        task_name="입고검사(3차원 측정)",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PLAN_LINKED,
    ),
    RuleMaster(
        task_code="TM-002",
        wg="시험",
        task_name="정기 신뢰성 시험",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="TM-003",
        wg="시험",
        task_name="의뢰품 측정",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="TM-004",
        wg="시험",
        task_name="고품 분석 시험(검사)",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="TM-005",
        wg="시험",
        task_name="시험실 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    # ── 공통 ──
    RuleMaster(
        task_code="CM-002",
        wg="공통",
        task_name="부적합품 등록 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="CM-003",
        wg="공통",
        task_name="부적합 판정 및 격리조치",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="CM-004",
        wg="공통",
        task_name="부적합품 폐기 처리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-005",
        wg="공통",
        task_name="부적합품 재활용(리워크)",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="CM-006",
        wg="공통",
        task_name="MQIR 개선 유효성 점검",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
    ),
    RuleMaster(
        task_code="CM-007",
        wg="공통",
        task_name="한도견본 및 마스터 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-008",
        wg="공통",
        task_name="측정장비 관리 및 측정 준비",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-009",
        wg="공통",
        task_name="검교정 관리",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-010",
        wg="공통",
        task_name="게이지 R&R",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-011",
        wg="공통",
        task_name="검사원 업무일지 작성",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-001",
        wg="공통",
        task_name="품질 미팅",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="CM-012",
        wg="공통",
        task_name="재고 실사",
        task_type=TaskType.QUANTITATIVE,
        unit_time_method="직접입력",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    # ── 정성 업무 ──
    RuleMaster(
        task_code="QL-001",
        wg="공통",
        task_name="상주원",
        task_type=TaskType.QUALITATIVE,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="QL-002",
        wg="공통",
        task_name="전진관리",
        task_type=TaskType.QUALITATIVE,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="QL-003",
        wg="공통",
        task_name="CS-RS",
        task_type=TaskType.QUALITATIVE,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="QL-004",
        wg="공통",
        task_name="고품분석",
        task_type=TaskType.QUALITATIVE,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    # ── 표준외 인원 ──
    RuleMaster(
        task_code="NS-001",
        wg="공통",
        task_name="그룹장",
        task_type=TaskType.NON_STANDARD,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="NS-002",
        wg="공통",
        task_name="파트장",
        task_type=TaskType.NON_STANDARD,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
    RuleMaster(
        task_code="NS-003",
        wg="공통",
        task_name="지원조",
        task_type=TaskType.NON_STANDARD,
        unit_time_method="해당없음",
        frequency_method=FrequencyMethod.PERIODIC,
    ),
]


class RuleMasterRegistry:
    """업무 마스터 조회·수정 레지스트리."""

    def __init__(self, rules: list[RuleMaster] | None = None) -> None:
        self._rules: list[RuleMaster] = deepcopy(rules if rules is not None else _DEFAULT_RULES)
        self._by_code: dict[str, RuleMaster] = {r.task_code: r for r in self._rules}

    def get_all(self) -> list[RuleMaster]:
        return deepcopy(self._rules)

    def get_by_task_code(self, task_code: str) -> RuleMaster | None:
        rule = self._by_code.get(task_code)
        return deepcopy(rule) if rule else None

    def get_by_wg_and_task_name(self, wg: str, task_name: str) -> RuleMaster | None:
        for rule in self._rules:
            if rule.wg == wg and rule.task_name == task_name:
                return deepcopy(rule)
        return None

    def get_by_wg(self, wg: str) -> list[RuleMaster]:
        return deepcopy([r for r in self._rules if r.wg == wg])

    def get_by_task_type(self, task_type: TaskType) -> list[RuleMaster]:
        return deepcopy([r for r in self._rules if r.task_type == task_type])

    def get_quantitative_rules(self) -> list[RuleMaster]:
        return self.get_by_task_type(TaskType.QUANTITATIVE)

    def get_qualitative_rules(self) -> list[RuleMaster]:
        return self.get_by_task_type(TaskType.QUALITATIVE)

    def get_non_standard_rules(self) -> list[RuleMaster]:
        return self.get_by_task_type(TaskType.NON_STANDARD)

    def get_frequency_method(self, task_code: str) -> FrequencyMethod | None:
        rule = self._by_code.get(task_code)
        return rule.frequency_method if rule else None

    def update_rule(self, updated: RuleMaster) -> None:
        if updated.task_code not in self._by_code:
            raise KeyError(f"업무 코드 '{updated.task_code}'를 찾을 수 없습니다.")
        for idx, rule in enumerate(self._rules):
            if rule.task_code == updated.task_code:
                self._rules[idx] = updated
                self._by_code[updated.task_code] = updated
                return

    def add_rule(self, rule: RuleMaster) -> None:
        if rule.task_code in self._by_code:
            raise ValueError(f"업무 코드 '{rule.task_code}'가 이미 존재합니다.")
        self._rules.append(rule)
        self._by_code[rule.task_code] = rule

    def reset_to_default(self) -> None:
        self.__init__()

    def count_by_frequency_method(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rule in self._rules:
            if rule.task_type != TaskType.QUANTITATIVE:
                continue
            key = rule.frequency_method.value
            counts[key] = counts.get(key, 0) + 1
        return counts


_default_registry = RuleMasterRegistry()


def build_rule_master() -> list[RuleMaster]:
    """기본 rule master 전체 목록 반환."""
    return RuleMasterRegistry().get_all()


def get_rule_by_task_code(task_code: str) -> RuleMaster | None:
    return _default_registry.get_by_task_code(task_code)


def get_rule_by_wg_and_task_name(wg: str, task_name: str) -> RuleMaster | None:
    return _default_registry.get_by_wg_and_task_name(wg, task_name)


def get_rules_by_wg(wg: str) -> list[RuleMaster]:
    return _default_registry.get_by_wg(wg)


def get_quantitative_rules() -> list[RuleMaster]:
    return _default_registry.get_quantitative_rules()


def get_qualitative_rules() -> list[RuleMaster]:
    return _default_registry.get_qualitative_rules()


def get_non_standard_rules() -> list[RuleMaster]:
    return _default_registry.get_non_standard_rules()


def get_frequency_method_for_task(task_code: str) -> FrequencyMethod | None:
    return _default_registry.get_frequency_method(task_code)
