"""Offline tests for FusionOffice-Bench (issue #56).

Validators graded against hand-built OOXML zip fixtures (pure stdlib, no
office libs). Seed-dependent materialize/grade tests skip when the repo-root
venv (office libs) is absent, e.g. CI.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fusion_bench.office_bench.runner import build_summary, to_harness_task
from fusion_bench.office_bench.seedgen import root_python_available
from fusion_bench.office_bench.tasks import OFFICE_TASKS
from fusion_bench.office_bench.validators import validate

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _xlsx_bytes(sheets: dict[str, str], formula_cells: int = 0, const_cells: int = 0) -> bytes:
    buf = __import__("io").BytesIO()
    sheet_names = list(sheets)
    wb_sheets = "".join(f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(sheet_names))
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL_DOC}"><sheets>{wb_sheets}</sheets></workbook>',
        )
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Type="t" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(sheet_names))
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
        )
        for i, _n in enumerate(sheet_names):
            cells = "".join(
                f'<c r="B{r + 1}"{"><f>SUM(B2:B5)</f><v>1</v></c>" if r < formula_cells else "/>"}'
                for r in range(max(formula_cells, 1))
            )
            consts = "".join('<c r="C1" t="n"><v>42</v></c>' for _ in range(const_cells))
            zf.writestr(
                f"xl/worksheets/sheet{i + 1}.xml",
                f'<worksheet xmlns="{NS_MAIN}"><sheetData>{cells}{consts}</sheetData></worksheet>',
            )
    return buf.getvalue()


def _docx_bytes(paragraphs: list[str]) -> bytes:
    buf = __import__("io").BytesIO()
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", f'<w:document xmlns:w="{ns_w}"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def _pptx_bytes(slide_texts: list[str]) -> bytes:
    buf = __import__("io").BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i, texts in enumerate(slide_texts, start=1):
            runs = "".join(f"<a:t>{t}</a:t>" for t in texts)
            zf.writestr(
                f"ppt/slides/slide{i}.xml",
                f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                f'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{runs}</p:sld>',
            )
    return buf.getvalue()


class TestValidators:
    def test_xlsx_ok_require(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(_xlsx_bytes({"Sales": "rId1"}, formula_cells=1))
        score, detail = validate("office_xlsx", p, {"required_sheets": ["Sales"], "formula_policy": "require"})
        assert (score, detail) == (1.0, "ok")

    def test_xlsx_missing_sheet(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(_xlsx_bytes({"Data": "rId1"}))
        score, detail = validate("office_xlsx", p, {"required_sheets": ["Revenue"]})
        assert score == 0.0
        assert "sheet:Revenue" in detail

    def test_xlsx_require_no_formula(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(_xlsx_bytes({"Sales": "rId1"}, formula_cells=0))
        score, detail = validate("office_xlsx", p, {"required_sheets": ["Sales"], "formula_policy": "require"})
        assert score == 0.0
        assert "formula_cells=0" in detail

    def test_xlsx_strict_fails_on_constant(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(_xlsx_bytes({"Budget": "rId1"}, formula_cells=1, const_cells=1))
        score, detail = validate("office_xlsx", p, {"required_sheets": ["Budget"], "formula_policy": "strict"})
        assert score == 0.0
        assert "constant_numeric=1" in detail

    def test_xlsx_not_a_zip(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(b"garbage")
        score, _ = validate("office_xlsx", p, {"required_sheets": ["Sales"]})
        assert score == 0.0

    def test_xlsx_unknown_type(self, tmp_path: Path):
        p = tmp_path / "x.txt"
        p.write_text("hi")
        score, detail = validate("office_other", p, {})
        assert score == 0.0
        assert "unknown task_type" in detail

    def test_docx_ok_and_missing(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes(["Draft Report", "Pilot succeeded."]))
        ok, _ = validate("office_docx", p, {"required_sections": ["pilot succeeded."]})
        assert ok == 1.0
        score, detail = validate("office_docx", p, {"required_sections": ["Missing"]})
        assert score == 0.0
        assert "section:Missing" in detail

    def test_docx_not_a_zip(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(b"nope")
        score, _ = validate("office_docx", p, {"required_sections": ["x"]})
        assert score == 0.0

    def test_pptx_ok(self, tmp_path: Path):
        p = tmp_path / "a.pptx"
        p.write_bytes(_pptx_bytes([["Kickoff", "intro"], ["Agenda", "plan"], ["Budget"]]))
        score, detail = validate("office_pptx", p, {"min_slides": 3, "required_titles": ["kickoff", "budget"]})
        assert (score, detail) == (1.0, "ok")

    def test_pptx_too_few_slides(self, tmp_path: Path):
        p = tmp_path / "a.pptx"
        p.write_bytes(_pptx_bytes([["Kickoff"]]))
        score, detail = validate("office_pptx", p, {"min_slides": 4})
        assert score == 0.0
        assert "slides" in detail

    def test_pptx_missing_title(self, tmp_path: Path):
        p = tmp_path / "a.pptx"
        p.write_bytes(_pptx_bytes([["Kickoff"], ["Agenda"]]))
        score, detail = validate("office_pptx", p, {"min_slides": 2, "required_titles": ["Q&A"]})
        assert score == 0.0
        assert "title:Q&A" in detail


class TestTaskDefs:
    def test_32_tasks_three_axes(self):
        assert len(OFFICE_TASKS) == 32
        by_type = {t.task_type for t in OFFICE_TASKS}
        assert by_type == {"office_xlsx", "office_docx", "office_pptx"}
        counts = {ty: sum(1 for t in OFFICE_TASKS if t.task_type == ty) for ty in by_type}
        assert counts["office_xlsx"] == 12
        assert counts["office_docx"] == 10
        assert counts["office_pptx"] == 10

    def test_steps_axis(self):
        for t in OFFICE_TASKS:
            assert t.steps in (1, 2, 3), t.task_id
        assert {t.steps for t in OFFICE_TASKS} == {1, 2, 3}

    def test_unique_ids_and_instructions_point_at_root_python(self):
        ids = [t.task_id for t in OFFICE_TASKS]
        assert len(ids) == len(set(ids))
        for t in OFFICE_TASKS:
            assert t.instruction.strip(), t.task_id

    def test_verifier_pass_and_fail(self, tmp_path: Path):
        task = next(t for t in OFFICE_TASKS if t.task_id == "docx-create-meeting-notes")
        harness = to_harness_task(task)
        missing = harness.verifier(tmp_path)
        assert missing[0] is False
        assert "not a readable docx" in missing[1]
        p = tmp_path / task.result_file
        p.write_bytes(_docx_bytes(["Meeting Notes", "Budget approved for 2027.", "Owners assigned."]))
        ok = harness.verifier(tmp_path)
        assert ok == (True, "ok")


class TestSummary:
    def test_build_summary_layout(self):
        results = [
            {"task_type": "office_xlsx", "passed": True, "model": "m1"},
            {"task_type": "office_xlsx", "passed": False, "model": "m1"},
            {"task_type": "office_docx", "passed": True, "model": "m1"},
        ]
        summary = build_summary(results, run_id="office-abc", created_at="2026-11-25T00:00:00+00:00")
        assert summary["run_id"] == "office-abc"
        assert summary["models"] == {"fusion-harness": "m1"}
        arm = summary["arms"]["fusion-harness"]
        assert arm["total"] == 3
        assert arm["passed"] == 2
        assert arm["pass_rate"] == round(2 / 3, 4)
        assert arm["by_type"] == {
            "office_xlsx": {"passed": 1, "total": 2, "pass_rate": 0.5},
            "office_docx": {"passed": 1, "total": 1, "pass_rate": 1.0},
        }

    def test_build_summary_empty(self):
        summary = build_summary([], run_id="r", created_at="t")
        arm = summary["arms"]["fusion-harness"]
        assert arm["total"] == 0 and arm["pass_rate"] == 0.0 and arm["by_type"] == {}


@pytest.mark.skipif(not root_python_available(), reason="repo-root venv with office libs unavailable")
class TestSeedAndGrade:
    def test_materialize_then_grade_seedfile(self, tmp_path: Path):
        task = next(t for t in OFFICE_TASKS if t.task_id == "xlsx-total-formula")
        task.materialize(tmp_path)
        score, detail = task.grade(tmp_path)
        assert score == 0.0
        assert "formula_cells=0" in detail

    def test_materialize_all_seed_tasks(self, tmp_path: Path):
        for task in OFFICE_TASKS:
            if task.seed_files:
                ws = tmp_path / task.task_id
                task.materialize(ws)
                assert all((ws / rel).is_file() for rel in task.seed_files), task.task_id

    def test_grade_create_task_after_agent_edit(self, tmp_path: Path):
        task = next(t for t in OFFICE_TASKS if t.task_id == "xlsx-total-formula")
        task.materialize(tmp_path)
        add_formula = (
            "import openpyxl\n"
            "wb = openpyxl.load_workbook('sales.xlsx')\n"
            "ws = wb['Sales']\n"
            "ws['B6'] = '=SUM(B2:B5)'\n"
            "wb.save('sales.xlsx')\n"
        )
        import subprocess

        from fusion_bench.office_bench.seedgen import ROOT_PYTHON

        proc = subprocess.run(
            [str(ROOT_PYTHON), "-c", add_formula], cwd=tmp_path, capture_output=True, text=True, timeout=60
        )
        assert proc.returncode == 0, proc.stderr
        score, detail = task.grade(tmp_path)
        assert (score, detail) == (1.0, "ok")
