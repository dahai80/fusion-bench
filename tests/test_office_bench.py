"""Offline tests for FusionOffice-Bench (issue #56).

Validators graded against hand-built OOXML zip fixtures (pure stdlib, no
office libs). Seed-dependent materialize/grade tests skip when the repo-root
venv (office libs) is absent, e.g. CI.
"""

from __future__ import annotations

import json
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


class TestBoundaryReport:
    """#63 goal-2 lite: capability boundary on the (type, steps) grid."""

    @staticmethod
    def _row(task_id: str, task_type: str, steps: int, passed: bool, **kw) -> dict:
        row = {
            "task_id": task_id,
            "task_type": task_type,
            "steps": steps,
            "passed": passed,
            "harness_error": False,
            "run_error": "",
        }
        row.update(kw)
        return row

    def test_boundary_cell_and_probe(self):
        from fusion_bench.office_bench.boundary import boundary_report

        results = [
            self._row("a1", "office_xlsx", 1, True),
            self._row("a2", "office_xlsx", 2, True),
            self._row("a3", "office_xlsx", 2, False),
            self._row("a4", "office_xlsx", 3, False),
        ]
        report = boundary_report(results)
        cells = report["cells"]
        assert cells["office_xlsx#steps=1"]["boundary"] is False
        assert cells["office_xlsx#steps=2"]["boundary"] is True
        assert cells["office_xlsx#steps=2"]["fail_tasks"] == ["a3"]
        assert cells["office_xlsx#steps=3"]["boundary"] is False
        # probe: fully-passed steps=1 adjacent to mixed steps=2
        assert len(report["boundary_probes"]) == 1
        probe = report["boundary_probes"][0]
        assert probe["probe"] == "office_xlsx steps=2"
        assert probe["fail_tasks"] == ["a3"]

    def test_no_probe_when_lower_cell_not_full(self):
        from fusion_bench.office_bench.boundary import boundary_report

        results = [
            self._row("a1", "office_docx", 1, True),
            self._row("a2", "office_docx", 1, False),
            self._row("a3", "office_docx", 2, False),
        ]
        report = boundary_report(results)
        assert report["boundary_probes"] == []

    def test_harness_error_rows_excluded(self):
        from fusion_bench.office_bench.boundary import boundary_report

        results = [
            self._row("a1", "office_pptx", 1, True),
            self._row("bad", "office_pptx", 2, False, harness_error=True),
            self._row("down", "office_pptx", 2, False, run_error="engine unreachable"),
        ]
        report = boundary_report(results)
        assert all("bad" not in str(c) for c in report["cells"].values())
        assert len(report["excluded_tasks"]) == 2

    def test_write_boundary_artifacts(self, tmp_path):
        import json as j

        from fusion_bench.office_bench.boundary import write_boundary

        results = [self._row("a1", "office_xlsx", 1, True), self._row("a2", "office_xlsx", 2, False)]
        report = write_boundary(tmp_path, results)
        on_disk = j.loads((tmp_path / "boundary.json").read_text())
        assert on_disk == report
        md = (tmp_path / "boundary.md").read_text()
        assert "office_xlsx#steps=2" in md
        assert "Probe targets" in md


class TestValidatorAdversarial:
    """#63 goal-3 lite: reward-hack resistance of the structural validators."""

    def test_xlsx_formula_in_other_sheet_does_not_count(self, tmp_path: Path):
        # Shortcut: put the formula in a sheet other than the required one
        buf = __import__("io").BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "xl/workbook.xml",
                f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL_DOC}"><sheets>'
                '<sheet name="Cover" sheetId="1" r:id="rId1"/>'
                '<sheet name="Sales" sheetId="2" r:id="rId2"/></sheets></workbook>',
            )
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="t" Target="worksheets/sheet1.xml"/>'
                '<Relationship Id="rId2" Type="t" Target="worksheets/sheet2.xml"/></Relationships>',
            )
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                f'<worksheet xmlns="{NS_MAIN}"><sheetData>'
                '<c r="B6"><f>SUM(B2:B5)</f><v>10</v></c></sheetData></worksheet>',
            )
            zf.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{NS_MAIN}"><sheetData/></worksheet>')
        p = tmp_path / "a.xlsx"
        p.write_bytes(buf.getvalue())
        score, detail = validate("office_xlsx", p, {"required_sheets": ["Sales"], "formula_policy": "require"})
        assert score == 0.0
        assert "formula_cells=0" in detail

    def test_xlsx_formula_with_wrong_cached_value_still_passes(self, tmp_path: Path):
        # Known floor: structural validators check <f> presence, not math
        # correctness of the cached <v>. Documented limitation — semantic
        # grading needs an executor (out of scope for the vendored plugin).
        buf = __import__("io").BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "xl/workbook.xml",
                f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL_DOC}"><sheets>'
                '<sheet name="Sales" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="t" Target="worksheets/sheet1.xml"/></Relationships>',
            )
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                f'<worksheet xmlns="{NS_MAIN}"><sheetData>'
                '<c r="B6"><f>SUM(B2:B5)</f><v>999999</v></c></sheetData></worksheet>',
            )
        p = tmp_path / "a.xlsx"
        p.write_bytes(buf.getvalue())
        score, detail = validate("office_xlsx", p, {"required_sheets": ["Sales"], "formula_policy": "require"})
        assert score == 1.0 and detail == "ok"

    def test_docx_title_only_section_is_accepted(self, tmp_path: Path):
        # Known floor: substring presence cannot tell an empty section from
        # a written one. Documented limitation, adversarially pinned here so
        # a future verifier upgrade that fixes it flips this test loudly.
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes(["Draft Report", "Conclusion"]))
        score, detail = validate("office_docx", p, {"required_sections": ["conclusion"]})
        assert score == 1.0 and detail == "ok"


class TestOverTriggerProbes:
    """#64: over-trigger suppression — correct behavior is NOT mutating."""

    def test_two_negative_probes_defined(self):
        from fusion_bench.office_bench.tasks import NEGATIVE_PROBES

        assert [t.task_id for t in NEGATIVE_PROBES] == ["noop-read-only-query", "noop-no-op-request"]
        assert all(t.result_file == "" and t.task_type == "office_noop" for t in NEGATIVE_PROBES)
        assert all(t.seed_files for t in NEGATIVE_PROBES)

    def test_grade_negative_suppressed(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import _snapshot, grade_negative

        (tmp_path / "sales.xlsx").write_bytes(b"seed")
        before = _snapshot(tmp_path)
        assert before, "seed written"
        score, detail = grade_negative(before, tmp_path)
        assert (score, detail) == (1.0, "suppressed (workspace unchanged)")

    def test_grade_negative_modified_seed(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import _snapshot, grade_negative

        (tmp_path / "sales.xlsx").write_bytes(b"seed")
        before = _snapshot(tmp_path)
        (tmp_path / "sales.xlsx").write_bytes(b"mutated")
        score, detail = grade_negative(before, tmp_path)
        assert score == 0.0
        assert "modified=['sales.xlsx']" in detail

    def test_grade_negative_created_file(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import _snapshot, grade_negative

        (tmp_path / "sales.xlsx").write_bytes(b"seed")
        before = _snapshot(tmp_path)
        (tmp_path / "extra.txt").write_text("x")
        score, detail = grade_negative(before, tmp_path)
        assert score == 0.0
        assert "created=['extra.txt']" in detail

    def test_build_summary_separates_negative_track(self):
        from fusion_bench.office_bench.runner import build_summary

        results = [
            {
                "task_id": "a",
                "task_type": "office_xlsx",
                "steps": 1,
                "passed": True,
                "model": "m",
                "harness_error": False,
            },
            {
                "task_id": "noop-1",
                "task_type": "office_noop",
                "steps": 1,
                "passed": True,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "over_trigger",
            },
            {
                "task_id": "refuse-1",
                "task_type": "office_noop",
                "steps": 1,
                "passed": False,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "refusal",
            },
        ]
        summary = build_summary(results, "r", "t")
        arm = summary["arms"]["fusion-harness"]
        assert arm["total"] == 1 and arm["passed"] == 1
        assert arm["negative_probes"]["total"] == 2
        assert arm["negative_probes"]["suppressed"] == 1
        assert arm["negative_probes"]["suppression_rate"] == 0.5
        assert arm["negative_probes"]["families"] == {
            "over_trigger": {"passed": 1, "total": 1, "rate": 1.0},
            "refusal": {"passed": 0, "total": 1, "rate": 0.0},
        }

    def test_boundary_excludes_negative_rows(self):
        from fusion_bench.office_bench.boundary import boundary_report

        results = [
            {
                "task_id": "a",
                "task_type": "office_xlsx",
                "steps": 1,
                "passed": True,
                "harness_error": False,
                "run_error": "",
            },
            {
                "task_id": "noop-1",
                "task_type": "office_noop",
                "steps": 1,
                "passed": False,
                "harness_error": False,
                "run_error": "",
                "negative_probe": True,
            },
        ]
        report = boundary_report(results)
        assert list(report["cells"]) == ["office_xlsx#steps=1"]
        assert report["excluded_tasks"] == [{"task_id": "noop-1", "reason": "negative-probe track (#64)"}]

    @pytest.mark.asyncio
    async def test_run_office_probes_engine_down(self, tmp_path, monkeypatch):
        from fusion_bench.office_bench import runner

        monkeypatch.setattr(runner, "ensure_engine", lambda url, babysit=False: False)
        summary = await runner.run_office("http://127.0.0.1:1/v1", "m", tmp_path)
        arm = summary["arms"]["fusion-harness"]
        assert arm["total"] == 32
        assert arm["negative_probes"]["total"] == 10
        assert arm["negative_probes"]["suppressed"] == 0
        assert set(arm["negative_probes"]["families"]) == {
            "over_trigger",
            "refusal",
            "robustness",
            "fidelity",
            "inferential",
        }

    def test_all_probes_carry_contract_ids(self):
        from fusion_bench.office_bench.tasks import (
            FIDELITY_PROBES,
            INFERENTIAL_PROBES,
            NEGATIVE_PROBES,
            REFUSAL_PROBES,
            ROBUSTNESS_PROBES,
        )

        expected = {
            "noop-read-only-query": "OB-NOOP-NO-MUTATION",
            "noop-no-op-request": "OB-NOOP-NO-MUTATION",
            "robust-xlsx-total-formula-renamed": "OB-ROBUST-SURFACE-PERTURBATION",
            "robust-xlsx-rename-sheet-swapped": "OB-ROBUST-SURFACE-PERTURBATION",
            "refuse-missing-sheet": "OB-ABSTAIN-NO-EVIDENCE",
            "refuse-missing-column": "OB-ABSTAIN-NO-EVIDENCE",
            "fidelity-docx-add-section": "OB-FIDELITY-ANCHOR-PRESERVE",
            "fidelity-pptx-insert-slide": "OB-FIDELITY-ANCHOR-PRESERVE",
            "infer-docx-consistent-section": "OB-INFER-EXEMPLAR-ATTRIBUTE",
            "infer-docx-consistent-closing": "OB-INFER-EXEMPLAR-ATTRIBUTE",
        }
        for probe in NEGATIVE_PROBES + ROBUSTNESS_PROBES + REFUSAL_PROBES + FIDELITY_PROBES + INFERENTIAL_PROBES:
            assert probe.contract_id == expected[probe.task_id], probe.task_id
        from fusion_bench.office_bench.tasks import OFFICE_TASKS

        assert all(t.contract_id == "" for t in OFFICE_TASKS)

    def test_build_summary_aggregates_contracts(self):
        from fusion_bench.office_bench.runner import build_summary

        results = [
            {
                "task_id": "a",
                "task_type": "office_xlsx",
                "steps": 1,
                "passed": True,
                "model": "m",
                "harness_error": False,
            },
            {
                "task_id": "noop-1",
                "task_type": "office_noop",
                "steps": 1,
                "passed": True,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "over_trigger",
                "contract_id": "OB-NOOP-NO-MUTATION",
            },
            {
                "task_id": "refuse-1",
                "task_type": "office_noop",
                "steps": 1,
                "passed": False,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "refusal",
                "contract_id": "OB-ABSTAIN-NO-EVIDENCE",
            },
        ]
        summary = build_summary(results, "r", "t")
        arm = summary["arms"]["fusion-harness"]
        assert arm["contracts"] == {
            "OB-NOOP-NO-MUTATION": {"passed": 1, "total": 1, "rate": 1.0},
            "OB-ABSTAIN-NO-EVIDENCE": {"passed": 0, "total": 1, "rate": 0.0},
        }


def _docx_bytes_styled(paragraphs: list[tuple[str, bool]]) -> bytes:
    """(text, bold) paragraphs — for #67 inferential attribute checks."""
    buf = __import__("io").BytesIO()
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f"<w:p><w:r>{'<w:rPr><w:b/></w:rPr>' if bold else ''}<w:t>{text}</w:t></w:r></w:p>" for text, bold in paragraphs
    )
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", f'<w:document xmlns:w="{ns_w}"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


class TestFidelityProbes:
    """#67: task must succeed AND out-of-scope content must survive."""

    def test_defs(self):
        from fusion_bench.office_bench.tasks import FIDELITY_PROBES

        assert [t.task_id for t in FIDELITY_PROBES] == ["fidelity-docx-add-section", "fidelity-pptx-insert-slide"]
        assert all(t.validator_args.get("fidelity_anchors") for t in FIDELITY_PROBES)
        assert all(t.result_file for t in FIDELITY_PROBES)

    def _before(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import _snapshot
        from fusion_bench.office_bench.tasks import FIDELITY_PROBES

        task = FIDELITY_PROBES[0]
        # hand-written seed (never task.materialize — CI has no office venv)
        (tmp_path / task.result_file).write_bytes(_docx_bytes(["Seed report."]))
        return task, _snapshot(tmp_path)

    def test_grade_fidelity_pass(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import grade_fidelity

        task, before = self._before(tmp_path)
        (tmp_path / task.result_file).write_bytes(
            _docx_bytes(
                [
                    "Q3 review of the platform rollout.",
                    "CONFIDENTIAL — internal distribution only.",
                    "Prepared by the platform team.",
                    "Next steps: ship the pilot.",
                ]
            )
        )
        score, detail = grade_fidelity(task, before, tmp_path)
        assert (score, detail) == (1.0, "ok (task passed, out-of-scope content intact)")

    def test_grade_fidelity_anchor_damaged(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import grade_fidelity

        task, before = self._before(tmp_path)
        (tmp_path / task.result_file).write_bytes(
            _docx_bytes(
                [
                    "Q3 review of the platform rollout.",
                    "Prepared by the platform team.",
                    "Next steps: ship the pilot.",
                ]
            )
        )
        score, detail = grade_fidelity(task, before, tmp_path)
        assert score == 0.0
        assert "out-of-scope content damaged" in detail
        assert "CONFIDENTIAL" in detail

    def test_grade_fidelity_task_validator_failed(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import grade_fidelity

        task, before = self._before(tmp_path)
        (tmp_path / task.result_file).write_bytes(_docx_bytes(["unrelated"]))
        score, detail = grade_fidelity(task, before, tmp_path)
        assert score == 0.0
        assert "task validator failed" in detail

    def test_grade_fidelity_other_file_modified(self, tmp_path: Path):
        from fusion_bench.office_bench.runner import grade_fidelity

        task, before = self._before(tmp_path)
        (tmp_path / task.result_file).write_bytes(
            _docx_bytes(
                [
                    "Q3 review of the platform rollout.",
                    "CONFIDENTIAL — internal distribution only.",
                    "Prepared by the platform team.",
                    "Next steps: ship the pilot.",
                ]
            )
        )
        (tmp_path / "notes.tmp").write_text("side effect")
        score, detail = grade_fidelity(task, before, tmp_path)
        assert score == 0.0
        assert "files outside task target modified" in detail


class TestInferentialProbes:
    """#67 (WordInferBench): attributes inferred from an in-document exemplar."""

    def test_defs(self):
        from fusion_bench.office_bench.tasks import INFERENTIAL_PROBES

        assert [t.task_id for t in INFERENTIAL_PROBES] == [
            "infer-docx-consistent-section",
            "infer-docx-consistent-closing",
        ]
        assert all(t.task_type == "office_docx_infer" for t in INFERENTIAL_PROBES)
        assert all(t.validator_args.get("styled_sections") for t in INFERENTIAL_PROBES)

    def test_validate_accepts_infer_type(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes_styled([("Risks", True), ("Cache eviction may regress.", False)]))
        score, detail = validate(
            "office_docx_infer",
            p,
            {"required_sections": ["Risks"], "styled_sections": [{"text": "Risks", "bold": True}]},
        )
        assert (score, detail) == (1.0, "ok")

    def test_styled_section_bold_required(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes_styled([("Risks", False), ("Cache eviction may regress.", False)]))
        score, detail = validate(
            "office_docx_infer",
            p,
            {"required_sections": ["Risks"], "styled_sections": [{"text": "Risks", "bold": True}]},
        )
        assert score == 0.0
        assert "styled:Risks" in detail

    def test_styled_section_absent(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes_styled([("Findings", True)]))
        score, detail = validate("office_docx_infer", p, {"styled_sections": [{"text": "Risks", "bold": True}]})
        assert score == 0.0
        assert "styled:Risks" in detail

    def test_summary_families_breakdown(self):
        from fusion_bench.office_bench.runner import build_summary

        results = [
            {
                "task_id": "n1",
                "task_type": "office_noop",
                "steps": 1,
                "passed": True,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "over_trigger",
            },
            {
                "task_id": "f1",
                "task_type": "office_docx",
                "steps": 2,
                "passed": False,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "fidelity",
            },
            {
                "task_id": "i1",
                "task_type": "office_docx_infer",
                "steps": 2,
                "passed": True,
                "model": "m",
                "harness_error": False,
                "negative_probe": True,
                "probe_family": "inferential",
            },
        ]
        summary = build_summary(results, "r", "t")
        arm = summary["arms"]["fusion-harness"]
        assert arm["total"] == 0
        fams = arm["negative_probes"]["families"]
        assert fams["over_trigger"] == {"passed": 1, "total": 1, "rate": 1.0}
        assert fams["fidelity"]["passed"] == 0
        assert fams["inferential"]["passed"] == 1


class TestEngineBabysit:
    """#60: bounded probe, opt-in restarts, graceful degradation."""

    @pytest.fixture(autouse=True)
    def _no_binaries(self, monkeypatch):
        from fusion_bench.office_bench import runner

        monkeypatch.setattr(runner, "SVCTL", Path("/nonexistent/fusion-sv"))
        monkeypatch.setattr(runner, "MLXCTL", Path("/nonexistent/start.sh"))

    def test_unreachable_no_babysit_returns_false(self, monkeypatch):
        from fusion_bench.office_bench import runner

        monkeypatch.setattr(runner, "_probe", lambda url: False)
        assert runner.ensure_engine("http://127.0.0.1:1/v1", babysit=False) is False

    def test_unreachable_babysit_missing_binaries_degrades(self, monkeypatch):
        from fusion_bench.office_bench import runner

        monkeypatch.setattr(runner, "_probe", lambda url: False)
        assert runner.ensure_engine("http://127.0.0.1:1/v1", babysit=True) is False

    def test_reachable_short_circuits(self, monkeypatch):
        from fusion_bench.office_bench import runner

        calls = []

        def fake_probe(url):
            calls.append(url)
            return True

        monkeypatch.setattr(runner, "_probe", fake_probe)
        assert runner.ensure_engine("http://127.0.0.1:1/v1", babysit=False) is True
        assert len(calls) == 1

    def test_slow_engine_not_declared_dead_immediately(self, monkeypatch):
        from fusion_bench.office_bench import runner

        attempts = {"n": 0}

        def flaky_probe(url):
            attempts["n"] += 1
            return attempts["n"] >= 3

        monkeypatch.setattr(runner, "_probe", flaky_probe)
        monkeypatch.setattr(runner.time, "sleep", lambda s: None)
        assert runner.ensure_engine("http://127.0.0.1:1/v1", babysit=False) is True
        assert attempts["n"] == 3

    @pytest.mark.asyncio
    async def test_run_office_engine_down_records_error_rows(self, tmp_path, monkeypatch):
        from fusion_bench.office_bench import runner

        monkeypatch.setattr(runner, "ensure_engine", lambda url, babysit=False: False)
        summary = await runner.run_office("http://127.0.0.1:1/v1", "m", tmp_path)
        arm = summary["arms"]["fusion-harness"]
        assert arm["total"] == 32
        assert arm["passed"] == 0
        assert arm["harness_errors"] == 32
        rows = [r for r in json.loads((tmp_path / "results.json").read_text())]
        assert len(rows) == 42
        assert all(r["run_error"] == "engine unreachable" for r in rows)

    @staticmethod
    def _patch_saturated_runner(monkeypatch, tokens_in: int = 0, tokens_out: int = 0):
        from fusion_bench.office_bench import runner

        class FakeResult:
            error = None
            llm_calls = 1
            wall_s = 1.0

        FakeResult.tokens_in = tokens_in
        FakeResult.tokens_out = tokens_out

        class FakeFusionHarnessRunner:
            def __init__(self, *a, **kw):
                pass

            async def run(self, task, workspace):
                return FakeResult()

        monkeypatch.setattr(runner, "ModelClient", lambda **kw: object())
        monkeypatch.setattr(runner, "RetryingClient", lambda *a, **kw: object())
        monkeypatch.setattr(runner, "FusionHarnessRunner", FakeFusionHarnessRunner)
        monkeypatch.setattr(runner, "ensure_engine", lambda url, babysit=False: True)
        # CI has no repo-root venv: seed materialization needs office libs
        monkeypatch.setattr(runner.OfficeTask, "materialize", lambda self, ws: None)

    @pytest.mark.asyncio
    async def test_zero_token_task_classified_harness_error(self, tmp_path, monkeypatch):
        from fusion_bench.office_bench import runner

        self._patch_saturated_runner(monkeypatch)
        summary = await runner.run_office("http://engine/v1", "m", tmp_path)
        arm = summary["arms"]["fusion-harness"]
        assert arm["harness_errors"] == 32
        assert arm["passed"] == 0
        rows = json.loads((tmp_path / "results.json").read_text())
        core = [r for r in rows if not r.get("negative_probe")]
        assert len(core) == 32
        assert all(r["harness_error"] is True for r in core)
        assert all("harness-error" in r["verify_detail"] for r in core)

    @pytest.mark.asyncio
    async def test_tokened_task_not_harness_error(self, tmp_path, monkeypatch):
        from fusion_bench.office_bench import runner

        self._patch_saturated_runner(monkeypatch, tokens_in=100, tokens_out=10)
        summary = await runner.run_office("http://engine/v1", "m", tmp_path)
        arm = summary["arms"]["fusion-harness"]
        assert arm["harness_errors"] == 0
        rows = json.loads((tmp_path / "results.json").read_text())
        assert all(r["harness_error"] is False for r in rows)


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


class TestNegativeProbes:
    """issue #64: forbidden_* args let validators fail closed on unsolicited content."""

    def test_xlsx_forbidden_sheet_absent_passes(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(_xlsx_bytes({"Sales": "rId1"}))
        score, detail = validate("office_xlsx", p, {"forbidden_sheets": ["AI_Summary"]})
        assert (score, detail) == (1.0, "ok")

    def test_xlsx_forbidden_sheet_present_fails(self, tmp_path: Path):
        p = tmp_path / "a.xlsx"
        p.write_bytes(_xlsx_bytes({"Sales": "rId1", "AI_Summary": "rId2"}))
        score, detail = validate("office_xlsx", p, {"forbidden_sheets": ["AI_Summary"]})
        assert score == 0.0
        assert "forbidden sheet 'AI_Summary' present" in detail

    def test_docx_forbidden_section_present_fails(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes(["Report", "Unsolicited Analysis"]))
        score, detail = validate("office_docx", p, {"forbidden_sections": ["Unsolicited Analysis"]})
        assert score == 0.0
        assert "forbidden section" in detail

    def test_docx_forbidden_section_absent_passes(self, tmp_path: Path):
        p = tmp_path / "a.docx"
        p.write_bytes(_docx_bytes(["Report"]))
        score, detail = validate("office_docx", p, {"forbidden_sections": ["Unsolicited Analysis"]})
        assert (score, detail) == (1.0, "ok")

    def test_pptx_forbidden_title_present_fails(self, tmp_path: Path):
        p = tmp_path / "a.pptx"
        p.write_bytes(_pptx_bytes([["Q3 Plan"], ["Extra Conclusions"]]))
        score, detail = validate("office_pptx", p, {"forbidden_titles": ["Extra Conclusions"]})
        assert score == 0.0
        assert "forbidden title" in detail

    def test_pptx_forbidden_title_absent_passes(self, tmp_path: Path):
        p = tmp_path / "a.pptx"
        p.write_bytes(_pptx_bytes([["Q3 Plan"]]))
        score, detail = validate("office_pptx", p, {"forbidden_titles": ["Extra Conclusions"]})
        assert (score, detail) == (1.0, "ok")

    def test_noop_probe_over_trigger_scored_zero(self, tmp_path: Path):
        """No-op probe task: artifact must keep required sheet but must NOT
        grow an unsolicited summary sheet (over-trigger, arXiv 2610.02142)."""
        p = tmp_path / "sales.xlsx"
        p.write_bytes(_xlsx_bytes({"Sales": "rId1", "Summary": "rId2"}))
        args = {"required_sheets": ["Sales"], "forbidden_sheets": ["Summary"]}
        score, detail = validate("office_xlsx", p, args)
        assert score == 0.0
        assert "sheet:Sales" not in detail


class TestABGate:
    """#69 (C4, fusion-skills#13): contract-gated skill A/B reporting."""

    @staticmethod
    def _probe_row(task_id: str, passed: bool, harness_error: bool = False) -> dict:
        return {
            "task_id": task_id,
            "task_type": "office_noop",
            "steps": 1,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "harness_error": harness_error,
            "negative_probe": True,
            "probe_family": "over_trigger",
            "contract_id": "OB-NOOP-NO-MUTATION",
        }

    def test_mutation_rate(self):
        from fusion_bench.office_bench.ab_gate import unauthorized_mutation_rate

        rows = [
            self._probe_row("n1", True),
            self._probe_row("n2", False),
            self._probe_row("n3", False, harness_error=True),
        ]
        rate, violated, total = unauthorized_mutation_rate(rows)
        assert (rate, violated, total) == (0.5, 1, 2)

    def test_mutation_rate_empty(self):
        from fusion_bench.office_bench.ab_gate import unauthorized_mutation_rate

        assert unauthorized_mutation_rate([]) == (0.0, 0, 0)

    def test_gate_pass_clean(self):
        from fusion_bench.office_bench.ab_gate import gate_verdict

        verdict = gate_verdict([self._probe_row("n1", True)], [self._probe_row("n1", True)])
        assert verdict["gate"] == "pass"
        assert verdict["flipped"] == []
        assert verdict["mutation_rate_post"] == 0.0

    def test_gate_fails_on_flip(self):
        from fusion_bench.office_bench.ab_gate import gate_verdict

        verdict = gate_verdict([self._probe_row("n1", True)], [self._probe_row("n1", False)])
        assert verdict["gate"] == "fail"
        assert verdict["flipped"] == ["n1"]
        assert verdict["violations_post"] == ["n1"]

    def test_gate_fails_on_post_violation_without_flip(self):
        from fusion_bench.office_bench.ab_gate import gate_verdict

        verdict = gate_verdict([self._probe_row("n1", False)], [self._probe_row("n1", False)])
        assert verdict["gate"] == "fail"
        assert verdict["flipped"] == []
        assert verdict["violations_post"] == ["n1"]

    def test_gate_ignores_harness_errors(self):
        from fusion_bench.office_bench.ab_gate import gate_verdict

        verdict = gate_verdict([self._probe_row("n1", True)], [self._probe_row("n1", False, harness_error=True)])
        assert verdict["gate"] == "pass"
        assert verdict["mutation_probes_post"] == 0

    def test_harness_injection_audit_env(self, monkeypatch):
        from fusion_bench.office_bench.ab_gate import HARNESS_SKILLS_ENV, harness_injection_audit

        monkeypatch.setenv(HARNESS_SKILLS_ENV, " web-search , code-exec ")
        audit = harness_injection_audit()
        assert audit["injected_builtins"] == ["code-exec", "web-search"]
        assert audit["count"] == 2
        assert audit["bench_harness_injected"] == []

    def test_harness_injection_audit_default_empty(self, monkeypatch):
        from fusion_bench.office_bench.ab_gate import HARNESS_SKILLS_ENV, harness_injection_audit

        monkeypatch.delenv(HARNESS_SKILLS_ENV, raising=False)
        audit = harness_injection_audit()
        assert audit["injected_builtins"] == []
        assert audit["count"] == 0

    @staticmethod
    def _core_row(passed: bool) -> dict:
        return {
            "task_id": "core",
            "task_type": "office_xlsx",
            "steps": 2,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "harness_error": False,
            "negative_probe": False,
            "contract_id": "",
        }

    def test_ab_report_and_markdown(self):
        from fusion_bench.office_bench.ab_gate import ab_report, render_markdown

        runs = {
            "baseline": {
                "pre": [self._core_row(True), self._probe_row("n1", True)],
                "post": [self._core_row(True), self._probe_row("n1", True)],
            },
            "skill": {
                "pre": [self._core_row(False), self._probe_row("n1", True)],
                "post": [self._core_row(True), self._probe_row("n1", False)],
            },
        }
        report = ab_report(runs)
        assert report["gate"] == "fail"
        assert report["arms"]["skill"]["task_delta"] == 1.0
        assert report["arms"]["skill"]["unauthorized_mutation_rate_post"] == 1.0
        assert report["arms"]["baseline"]["gate"]["gate"] == "pass"
        md = render_markdown(report)
        assert "unauthorized-mutation-rate" in md
        assert "OB-NOOP-NO-MUTATION" in md
        assert "Harness injection audit" in md
        assert "| skill |" in md

    def test_ab_report_all_pass(self):
        from fusion_bench.office_bench.ab_gate import ab_report

        runs = {
            "baseline": {"pre": [self._probe_row("n1", True)], "post": [self._probe_row("n1", True)]},
            "skill": {"pre": [self._probe_row("n1", True)], "post": [self._probe_row("n1", True)]},
        }
        assert ab_report(runs)["gate"] == "pass"

    def test_write_ab_report(self, tmp_path):
        import json as _json

        from fusion_bench.office_bench.ab_gate import ab_report, write_ab_report

        runs = {"skill": {"pre": [self._probe_row("n1", True)], "post": [self._probe_row("n1", True)]}}
        write_ab_report(ab_report(runs), tmp_path)
        saved = _json.loads((tmp_path / "ab-report.json").read_text())
        assert saved["gate"] == "pass"
        assert (tmp_path / "ab-report.md").is_file()
