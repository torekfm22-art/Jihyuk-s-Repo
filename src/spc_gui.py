"""
SPC 공정능력 분석 — GUI (CustomTkinter)

실행:
    python src/spc_gui.py
    또는 run_spc_app.bat 더블클릭
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

if not getattr(sys, "frozen", False):
    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

from config.app_paths import get_project_root, is_frozen
from config.settings import INPUT_PATH, OUTPUT_PATH
from src.spc.excel_reader import detect_file_format, list_sheet_names

ROOT = get_project_root()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

FILE_TYPES = [
    ("Excel/CSV", "*.xlsx;*.xls;*.xlsm;*.csv"),
    ("Excel", "*.xlsx;*.xls;*.xlsm"),
    ("All", "*.*"),
]

STAGE_OPTIONS: list[tuple[str, str]] = [
    ("mass_production", "양산"),
    ("development", "개발"),
    ("pilot", "파일럿"),
    ("pre_mass_production", "양산 전"),
]
STAGE_LABEL_TO_VALUE = {label: value for value, label in STAGE_OPTIONS}
STAGE_VALUE_TO_LABEL = {value: label for value, label in STAGE_OPTIONS}

CHART_OPTIONS: list[tuple[str, str]] = [
    ("auto", "자동 선택"),
    ("xbar_s", "X-bar S"),
    ("xbar_r", "X-bar R"),
    ("imr", "I-MR"),
]
CHART_LABEL_TO_VALUE = {label: value for value, label in CHART_OPTIONS}

COLOR_OK = ("#1a7f4e", "#2ecc71")
COLOR_WARN = ("#9a6b00", "#f39c12")
COLOR_BAD = ("#a82828", "#e74c3c")
COLOR_NEUTRAL = ("gray20", "gray80")


def format_label(path: Path) -> str:
    fmt = detect_file_format(path)
    if fmt.value == "encrypted":
        return "암호화 Excel"
    if fmt.value == "xls" and path.suffix.lower() == ".xlsx":
        return "구형 xls"
    return fmt.value


def _verdict_color(text: str) -> tuple[str, str]:
    if text in ("안정", "정규", "충분", "가능"):
        return COLOR_OK
    if text in ("불안정", "비정규", "부족", "불가", "판정불가"):
        return COLOR_BAD
    if text in ("경계", "조건부", "예외적 가능"):
        return COLOR_WARN
    return COLOR_NEUTRAL


class SpcApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("SPC / 품질 분석")
        self.geometry("1100x780")
        self.minsize(960, 680)

        self._attached: list[Path] = []
        self._busy = False
        self._last_excel: Path | None = None
        self._last_pdf: Path | None = None

        self._vars = {
            "usl": tk.StringVar(value="10.50"),
            "lsl": tk.StringVar(value="9.50"),
            "process": tk.StringVar(value=""),
            "characteristic": tk.StringVar(value=""),
            "item": tk.StringVar(value=""),
            "subgroup_size": tk.StringVar(value="5"),
            "n_subgroups": tk.StringVar(value="25"),
            "chart_type": tk.StringVar(value="X-bar S"),
            "report_title": tk.StringVar(value="SPC 및 공정능력 연구 보고서"),
            "process_name": tk.StringVar(value=""),
            "machine_name": tk.StringVar(value=""),
            "file_password": tk.StringVar(value=""),
            "stage": tk.StringVar(value="양산"),
            "special_characteristic": tk.BooleanVar(value=False),
            "customer_exception_mode": tk.BooleanVar(value=False),
            "process_change_detected": tk.BooleanVar(value=False),
            "customer_exception_reason": tk.StringVar(value=""),
        }

        self._result_labels: dict[str, ctk.CTkLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="SPC 공정능력 분석",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="MES/QMS 데이터 → 관리도 · 공정능력 · 자동 판정 보고서",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
        ).grid(row=1, column=0, sticky="w", pady=(0, 4))

        self._tabview = ctk.CTkTabview(self)
        self._tabview.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)

        spc_tab = self._tabview.add("SPC 공정능력")
        spc_tab.grid_columnconfigure(0, weight=3)
        spc_tab.grid_columnconfigure(1, weight=2)
        spc_tab.grid_rowconfigure(0, weight=1)

        self._build_spc_left(spc_tab)
        self._build_spc_right(spc_tab)

        try:
            from src.xy_matrix.gui_panel import XyMatrixPanel

            xy_tab = self._tabview.add("X-Y 매트릭스")
            xy_tab.grid_columnconfigure(0, weight=1)
            xy_tab.grid_rowconfigure(0, weight=1)
            xy_host = tk.Frame(xy_tab)
            xy_host.grid(row=0, column=0, sticky="nsew")
            xy_host.grid_columnconfigure(0, weight=1)
            xy_host.grid_rowconfigure(0, weight=1)
            XyMatrixPanel(xy_host, ROOT).grid(row=0, column=0, sticky="nsew")
        except Exception as exc:
            logger.warning("X-Y 매트릭스 탭 로드 실패: %s", exc)

        self._log(f"출력 폴더: {OUTPUT_PATH}")

    def _build_spc_left(self, parent: ctk.CTkFrame) -> None:
        left = ctk.CTkScrollableFrame(parent, label_text="분석 설정")
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 6), pady=4)
        left.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(left, text="데이터 파일", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 2)
        )
        row += 1
        self._file_box = ctk.CTkTextbox(left, height=88, font=ctk.CTkFont(size=12))
        self._file_box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=2)
        self._file_box.configure(state="disabled")
        row += 1

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        self._btn_add = ctk.CTkButton(btn_row, text="+ 파일 추가", width=100, command=self._add_files)
        self._btn_add.pack(side="left", padx=(0, 6))
        self._btn_remove = ctk.CTkButton(btn_row, text="- 마지막 제거", width=100, command=self._remove_selected)
        self._btn_remove.pack(side="left", padx=3)
        self._btn_clear = ctk.CTkButton(btn_row, text="전체 제거", width=80, command=self._clear_files)
        self._btn_clear.pack(side="left", padx=3)
        row += 1
        ctk.CTkLabel(
            left,
            text="군내 연속 5 · 일자 랜덤 · LOT·교대 구분 · 25군 권장",
            font=ctk.CTkFont(size=11),
            text_color="gray55",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 8))
        row += 1

        specs = [
            ("USL", "usl"),
            ("LSL", "lsl"),
            ("공정 필터", "process"),
            ("검사항목", "characteristic"),
            ("품목", "item"),
            ("Subgroup 크기", "subgroup_size"),
            ("Subgroup 수", "n_subgroups"),
            ("공정명(보고서)", "process_name"),
            ("설비/라인", "machine_name"),
        ]
        for label, key in specs:
            ctk.CTkLabel(left, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
            ctk.CTkEntry(left, textvariable=self._vars[key]).grid(row=row, column=1, sticky="ew", padx=6, pady=3)
            row += 1

        ctk.CTkLabel(left, text="공정 단계").grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ctk.CTkComboBox(
            left,
            values=[label for _, label in STAGE_OPTIONS],
            variable=self._vars["stage"],
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        row += 1

        opt_frm = ctk.CTkFrame(left, fg_color="transparent")
        opt_frm.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        ctk.CTkCheckBox(opt_frm, text="특별특성", variable=self._vars["special_characteristic"]).pack(side="left", padx=6)
        ctk.CTkCheckBox(opt_frm, text="고객 예외", variable=self._vars["customer_exception_mode"]).pack(side="left", padx=6)
        ctk.CTkCheckBox(opt_frm, text="공정변경", variable=self._vars["process_change_detected"]).pack(side="left", padx=6)
        row += 1

        ctk.CTkLabel(left, text="예외 사유").grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ctk.CTkEntry(left, textvariable=self._vars["customer_exception_reason"]).grid(
            row=row, column=1, sticky="ew", padx=6, pady=3
        )
        row += 1

        ctk.CTkLabel(left, text="관리도").grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ctk.CTkComboBox(
            left,
            values=[label for _, label in CHART_OPTIONS],
            variable=self._vars["chart_type"],
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        row += 1

        ctk.CTkLabel(left, text="파일 비밀번호").grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ctk.CTkEntry(left, textvariable=self._vars["file_password"], show="*").grid(
            row=row, column=1, sticky="ew", padx=6, pady=3
        )
        row += 1

        ctk.CTkLabel(left, text="보고서 제목").grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ctk.CTkEntry(left, textvariable=self._vars["report_title"]).grid(
            row=row, column=1, sticky="ew", padx=6, pady=3
        )
        row += 1

        act = ctk.CTkFrame(left, fg_color="transparent")
        act.grid(row=row, column=0, columnspan=2, pady=12)
        self._btn_sample = ctk.CTkButton(act, text="샘플 생성", width=100, command=self._gen_sample)
        self._btn_sample.pack(side="left", padx=4)
        self._btn_run = ctk.CTkButton(
            act, text="▶  분석 실행", width=120, height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._run_analysis,
        )
        self._btn_run.pack(side="left", padx=8)

    def _build_spc_right(self, parent: ctk.CTkFrame) -> None:
        right = ctk.CTkFrame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 4), pady=4)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            right, text="자동 판정 요약",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        cards = ctk.CTkFrame(right)
        cards.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        cards.grid_columnconfigure((0, 1), weight=1)

        card_defs = [
            ("process_stability", "공정상태", "—"),
            ("normality_verdict", "정규성", "—"),
            ("capability_verdict", "공정능력", "—"),
            ("control_chart_deploy", "관리도 적용", "—"),
        ]
        for i, (key, title, default) in enumerate(card_defs):
            fr = ctk.CTkFrame(cards)
            fr.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(fr, text=title, font=ctk.CTkFont(size=11), text_color="gray55").pack(anchor="w", padx=10, pady=(8, 0))
            lbl = ctk.CTkLabel(fr, text=default, font=ctk.CTkFont(size=18, weight="bold"))
            lbl.pack(anchor="w", padx=10, pady=(0, 8))
            self._result_labels[key] = lbl

        self._priority_label = ctk.CTkLabel(
            right, text="우선 조치: 분석 실행 후 표시됩니다.",
            font=ctk.CTkFont(size=12),
            wraplength=360,
            justify="left",
        )
        self._priority_label.grid(row=2, column=0, sticky="ew", padx=14, pady=6)

        self._progress = ctk.CTkProgressBar(right, mode="indeterminate")
        self._progress.grid(row=2, column=0, sticky="ew", padx=14, pady=(36, 0))
        self._progress.grid_remove()

        act = ctk.CTkFrame(right, fg_color="transparent")
        act.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 4))
        self._btn_open_excel = ctk.CTkButton(act, text="Excel", width=72, state="disabled", command=self._open_excel)
        self._btn_open_excel.pack(side="left", padx=3)
        self._btn_open_pdf = ctk.CTkButton(act, text="PDF", width=72, state="disabled", command=self._open_pdf)
        self._btn_open_pdf.pack(side="left", padx=3)
        self._btn_open_out = ctk.CTkButton(act, text="결과 폴더", width=88, command=self._open_output)
        self._btn_open_out.pack(side="left", padx=3)

        ctk.CTkLabel(right, text="실행 로그", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, sticky="nw", padx=12, pady=(8, 0)
        )
        self._log_box = ctk.CTkTextbox(right, font=ctk.CTkFont(family="Consolas", size=12))
        self._log_box.grid(row=3, column=0, sticky="nsew", padx=10, pady=(28, 10))

    def _log(self, msg: str) -> None:
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (
            self._btn_run, self._btn_add, self._btn_remove, self._btn_clear,
            self._btn_sample, self._btn_open_excel, self._btn_open_pdf,
        ):
            btn.configure(state=state)
        if busy:
            self._progress.grid()
            self._progress.start()
        else:
            self._progress.stop()
            self._progress.grid_remove()

    def _update_result_panel(self, decision) -> None:
        if decision is None:
            return
        v = decision.verdict_summary
        mapping = {
            "process_stability": v.process_stability,
            "normality_verdict": v.normality_verdict,
            "capability_verdict": v.capability_verdict,
            "control_chart_deploy": v.control_chart_deploy,
        }
        for key, text in mapping.items():
            lbl = self._result_labels.get(key)
            if lbl:
                lbl.configure(text=text, text_color=_verdict_color(text))
        self._priority_label.configure(text=f"우선 조치: {v.priority_action}")

    def _reset_result_panel(self) -> None:
        for lbl in self._result_labels.values():
            lbl.configure(text="—", text_color=COLOR_NEUTRAL)
        self._priority_label.configure(text="우선 조치: 분석 중...")
        self._btn_open_excel.configure(state="disabled")
        self._btn_open_pdf.configure(state="disabled")

    def _refresh_file_list(self) -> None:
        self._file_box.configure(state="normal")
        self._file_box.delete("1.0", "end")
        if not self._attached:
            self._file_box.insert("1.0", "(파일 없음 — 「+ 파일 추가」)")
        else:
            lines = [f"• {p.name}  [{format_label(p)}]" for p in self._attached]
            self._file_box.insert("1.0", "\n".join(lines))
        self._file_box.configure(state="disabled")

    def _add_paths(self, paths: list[str]) -> int:
        pwd = self._vars["file_password"].get() or None
        added = 0
        for raw in paths:
            p = Path(raw)
            if not p.exists():
                self._log(f"⚠ 파일 없음: {raw}")
                continue
            if p.resolve() in [x.resolve() for x in self._attached]:
                continue
            self._attached.append(p.resolve())
            added += 1
            self._log(f"첨부: {p.name} ({format_label(p)})")
            try:
                sheets = list_sheet_names(p, pwd)
                if sheets and sheets[0] != "CSV":
                    self._log(f"  시트: {', '.join(sheets[:4])}{'...' if len(sheets) > 4 else ''}")
            except Exception as exc:
                self._log(f"  ⚠ {exc}")
        self._refresh_file_list()
        return added

    def _add_files(self) -> None:
        if self._busy:
            return
        paths = filedialog.askopenfilenames(title="Excel/CSV 파일 선택", filetypes=FILE_TYPES)
        if paths:
            self._add_paths(list(paths))

    def _remove_selected(self) -> None:
        if self._attached:
            self._attached.pop()
            self._refresh_file_list()

    def _clear_files(self) -> None:
        self._attached.clear()
        self._refresh_file_list()

    def _gen_sample(self) -> None:
        def task():
            try:
                from src.spc.sample_data import generate_sample_files

                self._log("샘플 데이터 생성 중...")
                if is_frozen():
                    mes, qms = generate_sample_files(INPUT_PATH)
                else:
                    subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / "generate_sample_data.py")],
                        cwd=ROOT, check=True,
                    )
                    mes = Path(INPUT_PATH) / "mes_data.xlsx"
                    qms = Path(INPUT_PATH) / "qms_data.xlsx"
                self._attached.clear()
                self._add_paths([str(mes), str(qms)])
                self.after(0, lambda: messagebox.showinfo("완료", "샘플 파일 2건이 첨부되었습니다.\n「분석 실행」을 눌러주세요."))
            except Exception as exc:
                self._log(f"오류: {exc}")
                self.after(0, lambda: messagebox.showerror("오류", str(exc)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self._set_busy(True)
        threading.Thread(target=task, daemon=True).start()

    def _build_config(self):
        from src.spc.pipeline import SpcJobConfig

        if not self._attached:
            raise ValueError("Excel/CSV 파일을 1개 이상 첨부하세요.\n「+ 파일 추가」 버튼을 사용하세요.")

        v = self._vars
        stage_label = v["stage"].get()
        chart_label = v["chart_type"].get()
        stage = STAGE_LABEL_TO_VALUE.get(stage_label, "mass_production")
        chart_type = CHART_LABEL_TO_VALUE.get(chart_label, "xbar_s")

        return SpcJobConfig(
            input_files=[str(p) for p in self._attached],
            file_password=v["file_password"].get() or None,
            usl=float(v["usl"].get()),
            lsl=float(v["lsl"].get()),
            filter_process=v["process"].get() or None,
            filter_characteristic=v["characteristic"].get() or None,
            filter_item=v["item"].get() or None,
            subgroup_size=int(v["subgroup_size"].get()),
            n_subgroups=int(v["n_subgroups"].get()),
            chart_type=chart_type,  # type: ignore[arg-type]
            report_title=v["report_title"].get(),
            process_name=v["process_name"].get() or None,
            machine_name=v["machine_name"].get() or None,
            stage=stage,  # type: ignore[arg-type]
            special_characteristic=v["special_characteristic"].get(),
            customer_exception_mode=v["customer_exception_mode"].get(),
            process_change_detected=v["process_change_detected"].get(),
            customer_exception_reason=v["customer_exception_reason"].get() or None,
            output_dir=OUTPUT_PATH,
        )

    def _run_analysis(self) -> None:
        if self._busy:
            return

        def task():
            try:
                from src.spc.pipeline import SpcPipeline

                self.after(0, self._reset_result_panel)
                self._log("=" * 40)
                self._log("분석 시작...")
                result = SpcPipeline(self._build_config()).run()
                a = result.analysis
                self._log(f"원본 {result.raw_count}건 → 표본 {result.sample_count}건")
                self._log(f"관리도: {a.control_limits.chart_type}")
                self._log(f"정규성: {'정규' if a.normality.is_normal else '비정규'} (p={a.normality.p_value:.4f})")
                if a.capability:
                    c = a.capability
                    self._log(f"Cp={c.cp:.4f}, Cpk={c.cpk:.4f}")

                d = result.decision
                if d:
                    v = d.verdict_summary
                    self.after(0, lambda: self._update_result_panel(d))
                    self._log("── 자동 판정 요약 ──")
                    self._log(f"  공정상태: {v.process_stability}")
                    self._log(f"  정규성: {v.normality_verdict}")
                    self._log(f"  공정능력: {v.capability_verdict}")
                    self._log(f"  관리도 적용: {v.control_chart_deploy}")
                    self._log(f"  우선 조치: {v.priority_action}")
                    for entry in d.control_chart.decision_log[:5]:
                        self._log(f"  [{entry.rule_id}] {entry.message}")

                excel = result.report_paths.get("excel")
                pdf = result.report_paths.get("pdf")
                self._last_excel = Path(excel) if excel else None
                self._last_pdf = Path(pdf) if pdf else None
                self._log(f"Excel: {excel}")
                self._log(f"PDF:   {pdf}")
                self._log("분석 완료!")

                cpk = a.capability.cpk if a.capability else 0

                def on_done():
                    if self._last_excel and self._last_excel.exists():
                        self._btn_open_excel.configure(state="normal")
                    if self._last_pdf and self._last_pdf.exists():
                        self._btn_open_pdf.configure(state="normal")
                    messagebox.showinfo(
                        "분석 완료",
                        f"Cpk={cpk:.4f}\n\nExcel·PDF 보고서가 생성되었습니다.\n"
                        "오른쪽 「Excel」「PDF」 버튼으로 바로 열 수 있습니다.",
                    )

                self.after(0, on_done)
            except Exception as exc:
                logger.exception("분석 실패")
                self._log(f"오류: {exc}")
                self.after(0, lambda: messagebox.showerror("분석 실패", str(exc)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self._set_busy(True)
        threading.Thread(target=task, daemon=True).start()

    def _open_path(self, path: Path | None) -> None:
        if path and path.exists():
            os.startfile(str(path))
        else:
            messagebox.showwarning("파일 없음", "보고서 파일을 찾을 수 없습니다.")

    def _open_excel(self) -> None:
        self._open_path(self._last_excel)

    def _open_pdf(self) -> None:
        self._open_path(self._last_pdf)

    def _open_output(self) -> None:
        out = Path(OUTPUT_PATH)
        out.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(out)])


def main():
    try:
        SpcApp().mainloop()
    except Exception as exc:
        import traceback

        err = traceback.format_exc()
        try:
            messagebox.showerror("SPC 시작 오류", err)
        except Exception:
            print(err, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
