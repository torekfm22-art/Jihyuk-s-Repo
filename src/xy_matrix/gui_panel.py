"""
X-Y 매트릭스 분석 GUI 패널 (ttk, SPC 앱 탭용).
"""
from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from config.settings import OUTPUT_PATH

FILE_TYPES = [
    ("Excel/CSV", "*.xlsx;*.xls;*.xlsm;*.csv"),
    ("All", "*.*"),
]


class XyMatrixPanel(ttk.Frame):
    """Notebook 탭에 삽입하는 X-Y 매트릭스 분석 UI."""

    def __init__(self, master, project_root: Path, **kwargs):
        super().__init__(master, padding=10, **kwargs)
        self._root = project_root
        self._structure: dict | None = None

        self._file = tk.StringVar()
        self._sheet = tk.StringVar(value="0")
        self._y_col = tk.StringVar()
        self._run_multi = tk.BooleanVar(value=True)
        self._auto_open_chart = tk.BooleanVar(value=True)
        self._last_excel: Path | None = None
        self._last_chart: Path | None = None

        self._build()

    def _build(self) -> None:
        pad = {"padx": 6, "pady": 3}
        row = 0

        ttk.Label(
            self,
            text="X-Y 매트릭스 자동 분석 (Raw data 시트)",
            font=("Malgun Gothic", 12, "bold"),
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(0, 8))
        row += 1

        ttk.Label(self, text="데이터 파일").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self._file, width=48).grid(
            row=row, column=1, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(self, text="찾기", command=self._browse).grid(row=row, column=3, **pad)
        row += 1

        ttk.Label(self, text="시트").grid(row=row, column=0, sticky="w", **pad)
        self._sheet_combo = ttk.Combobox(
            self, textvariable=self._sheet, width=28, state="readonly"
        )
        self._sheet_combo.grid(row=row, column=1, sticky="w", **pad)
        ttk.Button(self, text="시트 목록", command=self._load_sheets).grid(
            row=row, column=2, sticky="w", **pad
        )
        row += 1

        ttk.Label(self, text="Y 인자").grid(row=row, column=0, sticky="w", **pad)
        self._y_combo = ttk.Combobox(
            self, textvariable=self._y_col, width=28, state="readonly"
        )
        self._y_combo.grid(row=row, column=1, sticky="w", **pad)
        ttk.Button(self, text="구조 인식", command=self._preview_structure).grid(
            row=row, column=2, sticky="w", **pad
        )
        row += 1

        ttk.Checkbutton(
            self, text="다중회귀 분석 (9·3점 인자)", variable=self._run_multi
        ).grid(row=row, column=1, sticky="w", **pad)
        ttk.Checkbutton(
            self, text="분석 후 파레토 차트 열기", variable=self._auto_open_chart
        ).grid(row=row, column=2, columnspan=2, sticky="w", **pad)
        row += 1

        act = ttk.Frame(self)
        act.grid(row=row, column=0, columnspan=4, pady=8)
        ttk.Button(act, text="XY 샘플 생성", command=self._gen_sample).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(act, text="분석 실행", command=self._run_analysis).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(act, text="결과 Excel", command=self._open_excel).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(act, text="파레토 차트", command=self._open_chart).pack(
            side=tk.LEFT, padx=4
        )
        row += 1

        ttk.Label(self, text="매트릭스 결과").grid(row=row, column=0, sticky="nw", **pad)
        tree_frm = ttk.Frame(self)
        tree_frm.grid(row=row, column=1, columnspan=3, sticky="nsew", **pad)
        self._tree = ttk.Treeview(tree_frm, height=7, show="headings")
        tree_scroll = ttk.Scrollbar(tree_frm, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        row += 1

        ttk.Label(self, text="로그").grid(row=row, column=0, sticky="nw", **pad)
        self.log = scrolledtext.ScrolledText(self, height=8, font=("Consolas", 9))
        self.log.grid(row=row, column=1, columnspan=3, sticky="nsew", **pad)
        self.rowconfigure(row, weight=1)
        self.columnconfigure(1, weight=1)

        self._log(
            "Raw 시트: 인자명↔유형 2행 헤더 지원 | XY_매트릭스 시트에 파레토·요약·CTP 통합"
        )

    def _log(self, msg: str) -> None:
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def _clear_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for col in self._tree["columns"]:
            self._tree.heading(col, text="")
            self._tree.column(col, width=0)

    def _fill_matrix_tree(self, matrix_display) -> None:
        self._clear_tree()
        if matrix_display is None or matrix_display.empty:
            return
        cols = list(matrix_display.columns)
        self._tree["columns"] = cols
        widths = {
            "순위": 40, "X 인자명": 120, "인자 유형": 70, "분석기법": 100,
            "R-Square": 72, "P-Value": 72, "점수": 44, "기호": 40, "해석": 140,
        }
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=widths.get(c, 80), anchor="center")
        for _, row in matrix_display.iterrows():
            values = [row.get(c, "") for c in cols]
            self._tree.insert("", tk.END, values=values)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(title="Raw data Excel", filetypes=FILE_TYPES)
        if path:
            self._file.set(path)
            self._load_sheets()

    def _resolve_sheet(self) -> str | int:
        s = self._sheet.get().strip()
        if not s:
            return 0
        if s.isdigit():
            return int(s)
        return s

    def _load_sheets(self) -> None:
        path = self._file.get().strip()
        if not path:
            messagebox.showwarning("안내", "파일을 선택하세요.")
            return
        try:
            from src.spc.excel_reader import list_sheet_names

            names = list_sheet_names(Path(path))
            if not names:
                names = ["0"]
            self._sheet_combo["values"] = names
            if names:
                raw_hint = next(
                    (n for n in names if "raw" in n.lower() or "원본" in n), names[0]
                )
                self._sheet.set(raw_hint)
            self._log(f"시트: {', '.join(names)}")
        except Exception as exc:
            self._log(f"시트 목록 오류: {exc}")

    def _preview_structure(self) -> None:
        path = self._file.get().strip()
        if not path:
            messagebox.showwarning("안내", "파일을 선택하세요.")
            return

        def task() -> None:
            try:
                from src.xy_matrix.data_detection import auto_detect_data_structure

                df, structure = auto_detect_data_structure(
                    path, sheet_name=self._resolve_sheet()
                )
                self._structure = structure
                ys = structure["y_columns"]
                xs = structure["x_columns"]
                all_cols = [
                    c for c in df.columns
                    if c not in structure.get("excluded_columns", [])
                ]
                self._y_combo["values"] = all_cols if all_cols else ys
                if ys:
                    self._y_col.set(ys[0])
                self._log("Y인자: 맨 왼쪽 열 우선 → " + (ys[0] if ys else "(없음)"))
                self._log(f"표본 {len(df)}행 | Y: {ys}")
                self._log(f"X ({len(xs)}): {', '.join(str(x) for x in xs)}")
                if structure.get("layout_hint"):
                    self._log(
                        f"레이아웃: {structure['layout_hint']} "
                        f"(유형행={structure.get('type_row')}, "
                        f"인자명행={structure.get('name_row')})"
                    )
            except Exception as exc:
                self._log(f"구조 인식 실패: {exc}")
                messagebox.showerror("구조 인식", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _gen_sample(self) -> None:
        def task() -> None:
            try:
                from src.xy_matrix.sample_data import generate_xy_raw_sample

                path = generate_xy_raw_sample()
                self._file.set(str(path))
                self._load_sheets()
                self._preview_structure()
                messagebox.showinfo("완료", f"샘플 생성:\n{path}")
            except Exception as exc:
                self._log(f"샘플 오류: {exc}")
                messagebox.showerror("오류", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _show_chart(self, chart_path: Path) -> None:
        if chart_path.exists():
            os.startfile(str(chart_path))

    def _run_analysis(self) -> None:
        path = self._file.get().strip()
        if not path:
            messagebox.showwarning("안내", "파일을 선택하세요.")
            return

        def task() -> None:
            try:
                from datetime import datetime

                from src.xy_matrix import analyze_xy_matrix
                from src.xy_matrix.output import format_matrix_as_text

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out = Path(OUTPUT_PATH) / f"xy_matrix_result_{ts}.xlsx"
                chart = Path(OUTPUT_PATH) / "charts" / f"xy_pareto_{ts}.png"

                self._log("=" * 36)
                self._log("X-Y 매트릭스 분석 시작...")
                result = analyze_xy_matrix(
                    path,
                    y_column=self._y_col.get() or None,
                    run_multiple_reg=self._run_multi.get(),
                    output_format="excel",
                    output_path=out,
                    sheet_name=self._resolve_sheet(),
                    pareto_chart_path=chart,
                )
                self._last_excel = out
                self._last_chart = (
                    Path(result["pareto_chart_path"])
                    if result.get("pareto_chart_path")
                    else None
                )

                disp = result["matrix_display"]
                self.after(0, lambda: self._fill_matrix_tree(disp))
                self._log("\n[ XY 매트릭스 ]")
                self._log(format_matrix_as_text(disp))
                if result.get("pareto_display") is not None:
                    self._log("\n[ 파레토 ]")
                    self._log(result["pareto_display"].to_string(index=False))

                rec = result["recommendations"]
                self._log(rec.get("summary", ""))
                self._log(f"Excel(표+차트): {out}")
                if self._last_chart:
                    self._log(f"파레토 PNG: {self._last_chart}")

                if self._auto_open_chart.get() and self._last_chart:
                    self.after(0, lambda: self._show_chart(self._last_chart))

                messagebox.showinfo(
                    "분석 완료",
                    f"{rec.get('summary', '')}\n\n"
                    f"Excel: {out}\n"
                    f"(XY_매트릭스 시트에 파레토 표·차트·요약 통합)\n\n"
                    f"파레토 PNG:\n{self._last_chart or '-'}",
                )
            except Exception as exc:
                self._log(f"분석 오류: {exc}")
                messagebox.showerror("분석 실패", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _open_excel(self) -> None:
        if self._last_excel and self._last_excel.exists():
            os.startfile(str(self._last_excel))
        else:
            messagebox.showinfo("안내", "먼저 분석을 실행하세요.")

    def _open_chart(self) -> None:
        if self._last_chart and self._last_chart.exists():
            self._show_chart(self._last_chart)
        else:
            messagebox.showinfo("안내", "파레토 차트가 없습니다. 분석을 실행하세요.")
