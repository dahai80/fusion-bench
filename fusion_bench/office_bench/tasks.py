"""Office testset (issue #56): 32 tasks across apps x steps.

Difficulty axis = steps (1-3 operations). Every task is a file-level edit
graded by a deterministic structural validator (validators.py, vendored from
fusion-trainer#90). Seed snippets run under the repo-root venv python
(openpyxl / python-docx / python-pptx available there).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .seedgen import materialize_seeds
from .validators import validate

OFFICE_PY = "/Users/dahai/fusion/.venv/bin/python"

SYSTEM_PROMPT = f"""You are an office-document agent working in a small sandbox workspace.
Use the python interpreter at {OFFICE_PY} — it has openpyxl, python-docx and python-pptx installed.
Reply with ONE bash command inside a ```bash fenced block.
After each command you will see its combined stdout/stderr output.
When the task is fully complete, reply with exactly: DONE
Never run destructive commands outside the workspace."""


@dataclass
class OfficeTask:
    task_id: str
    task_type: str
    app: str
    steps: int
    instruction: str
    seed_files: dict[str, str] = field(default_factory=dict)
    result_file: str = ""
    validator_args: dict = field(default_factory=dict)

    def materialize(self, workspace: Path) -> None:
        materialize_seeds(self.seed_files, workspace)

    def grade(self, workspace: Path) -> tuple[float, str]:
        if not self.result_file:
            raise ValueError(f"{self.task_id}: no result_file")
        return validate(self.task_type, workspace / self.result_file, self.validator_args)


def _xlsx(path: str, code: str) -> tuple[str, str]:
    return path, f"import openpyxl\n{code}\nwb.save({path!r})\n"


def _docx(path: str, code: str) -> tuple[str, str]:
    return path, f"import docx\n{code}\nd.save({path!r})\n"


def _pptx(path: str, code: str) -> tuple[str, str]:
    return path, f"from pptx import Presentation\n{code}\np.save({path!r})\n"


XLSX_SEED_SALES = _xlsx(
    "sales.xlsx",
    "wb = openpyxl.Workbook()\nws = wb.active\nws.title = 'Sales'\n"
    "rows = [('item', 'units'), ('pen', 12), ('book', 30), ('bag', 8), ('cup', 15)]\n"
    "[ws.append(r) for r in rows]",
)
XLSX_SEED_DATA = _xlsx(
    "data.xlsx",
    "wb = openpyxl.Workbook()\nws = wb.active\nws.title = 'Data'\n"
    "rows = [('region', 'amount'), ('east', 100), ('west', 250), ('north', 75)]\n"
    "[ws.append(r) for r in rows]",
)
XLSX_SEED_SCORES = _xlsx(
    "scores.xlsx",
    "wb = openpyxl.Workbook()\nws = wb.active\nws.title = 'Scores'\n"
    "rows = [('name', 'score'), ('ann', 90), ('bob', 75), ('cid', 88)]\n"
    "[ws.append(r) for r in rows]",
)
DOCX_SEED_REPORT = _docx(
    "report.docx",
    "d = docx.Document()\n"
    "d.add_heading('Draft Report', level=1)\n"
    "d.add_paragraph('This draft covers the pilot phase only.')\n"
    "d.add_paragraph('Preliminary numbers are included in the appendix.')",
)
DOCX_SEED_MINUTES = _docx(
    "minutes.docx",
    "d = docx.Document()\n"
    "d.add_heading('Meeting Minutes', level=1)\n"
    "d.add_paragraph('Attendees reviewed the roadmap.')\n"
    "d.add_paragraph('Action items will be distributed by email.')",
)
PPTX_SEED_DECK = _pptx(
    "deck.pptx",
    "p = Presentation()\n"
    "s1 = p.slides.add_slide(p.slide_layouts[0])\n"
    "s1.shapes.title.text = 'Kickoff'\n"
    "s2 = p.slides.add_slide(p.slide_layouts[1])\n"
    "s2.shapes.title.text = 'Agenda'\n"
    "s2.placeholders[1].text = 'intro\\nplan'",
)

OFFICE_TASKS: list[OfficeTask] = [
    OfficeTask(
        task_id="xlsx-total-formula",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=1,
        instruction=(
            "Open sales.xlsx. In sheet 'Sales', put a SUM formula in cell B6 that "
            "adds B2:B5 (do not type the number directly, use a real formula). Save in place."
        ),
        seed_files=dict([XLSX_SEED_SALES]),
        result_file="sales.xlsx",
        validator_args={"required_sheets": ["Sales"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="xlsx-rename-sheet",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=1,
        instruction=(
            "Open data.xlsx and rename its sheet 'Data' to 'Revenue'. Keep all cell content unchanged. Save in place."
        ),
        seed_files=dict([XLSX_SEED_DATA]),
        result_file="data.xlsx",
        validator_args={"required_sheets": ["Revenue"]},
    ),
    OfficeTask(
        task_id="xlsx-add-summary-sheet",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=2,
        instruction=(
            "Open sales.xlsx, keep sheet 'Sales' intact and add a new empty sheet "
            "named 'Summary' after it. Save in place."
        ),
        seed_files=dict([XLSX_SEED_SALES]),
        result_file="sales.xlsx",
        validator_args={"required_sheets": ["Sales", "Summary"]},
    ),
    OfficeTask(
        task_id="xlsx-strict-formula",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=2,
        instruction=(
            "Create a new workbook budget.xlsx with one sheet 'Budget'. Column A "
            "(A1:A4) holds the text labels rent, food, transport, total. Cell B5 must "
            "contain a SUM formula over B2:B4, and B2:B4 must stay EMPTY. The only "
            "numeric cell in the sheet must be the formula result. Save as budget.xlsx."
        ),
        seed_files={},
        result_file="budget.xlsx",
        validator_args={"required_sheets": ["Budget"], "formula_policy": "strict"},
    ),
    OfficeTask(
        task_id="xlsx-two-sheets-formulas",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=3,
        instruction=(
            "Create a workbook report.xlsx with sheets 'East' and 'West'. In each "
            "sheet, A1 is the label 'amount' and A2 contains a SUM formula over A3:A10 "
            "(cells A3:A10 stay empty). Save as report.xlsx."
        ),
        seed_files={},
        result_file="report.xlsx",
        validator_args={"required_sheets": ["East", "West"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="xlsx-average-formula",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=2,
        instruction=(
            "Open scores.xlsx. In sheet 'Scores', put an AVERAGE formula in cell B6 "
            "covering B2:B5 (use the AVERAGE function, not a typed number). Save in place."
        ),
        seed_files=dict([XLSX_SEED_SCORES]),
        result_file="scores.xlsx",
        validator_args={"required_sheets": ["Scores"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="xlsx-new-workbook-two-sheets",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=2,
        instruction=(
            "Create a new workbook plan.xlsx containing exactly two sheets named "
            "'H1' and 'H2' (no other sheets). Save as plan.xlsx."
        ),
        seed_files={},
        result_file="plan.xlsx",
        validator_args={"required_sheets": ["H1", "H2"]},
    ),
    OfficeTask(
        task_id="xlsx-copy-structure",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=3,
        instruction=(
            "Open data.xlsx. Add a new sheet named 'Backup' whose A1 equals 'region' "
            "and A2 equals 'east' (same as the first two labels in sheet 'Data', write "
            "the values directly). Save in place."
        ),
        seed_files=dict([XLSX_SEED_DATA]),
        result_file="data.xlsx",
        validator_args={"required_sheets": ["Data", "Backup"]},
    ),
    OfficeTask(
        task_id="xlsx-count-formula",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=2,
        instruction=(
            "Open scores.xlsx. In sheet 'Scores', put a COUNT formula in cell C1 "
            "that counts numeric cells in B2:B5. Save in place."
        ),
        seed_files=dict([XLSX_SEED_SCORES]),
        result_file="scores.xlsx",
        validator_args={"required_sheets": ["Scores"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="xlsx-append-row-formula",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=3,
        instruction=(
            "Open sales.xlsx. Append a new row: A7 = 'mug', B7 = 20. Then put a SUM "
            "formula in B8 covering B2:B7. Save in place."
        ),
        seed_files=dict([XLSX_SEED_SALES]),
        result_file="sales.xlsx",
        validator_args={"required_sheets": ["Sales"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="xlsx-quarter-workbook",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=3,
        instruction=(
            "Create a workbook quarters.xlsx with sheets 'Q1', 'Q2', 'Q3'. In sheet "
            "'Q1', cell A1 must contain a SUM formula over A2:A5 (A2:A5 empty). Save "
            "as quarters.xlsx."
        ),
        seed_files={},
        result_file="quarters.xlsx",
        validator_args={"required_sheets": ["Q1", "Q2", "Q3"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="xlsx-labels-only-strict",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=3,
        instruction=(
            "Create a workbook totals.xlsx, sheet 'Totals'. Column A (A1:A5) holds "
            "only text labels: alpha, beta, gamma, delta, total. Cell A6 must hold a "
            "COUNTA formula over A1:A5. No numeric constant cells anywhere in the "
            "sheet. Save as totals.xlsx."
        ),
        seed_files={},
        result_file="totals.xlsx",
        validator_args={"required_sheets": ["Totals"], "formula_policy": "strict"},
    ),
    OfficeTask(
        task_id="docx-add-section",
        task_type="office_docx",
        app="documents",
        steps=1,
        instruction=(
            "Open report.docx and add a new section: a paragraph whose text is "
            "'Recommendations' followed by a paragraph 'Pilot succeeded.' Save in place."
        ),
        seed_files=dict([DOCX_SEED_REPORT]),
        result_file="report.docx",
        validator_args={"required_sections": ["Recommendations", "Pilot succeeded."]},
    ),
    OfficeTask(
        task_id="docx-append-summary",
        task_type="office_docx",
        app="documents",
        steps=1,
        instruction=(
            "Open minutes.docx and append one paragraph with the exact text 'Next meeting: December.'. Save in place."
        ),
        seed_files=dict([DOCX_SEED_MINUTES]),
        result_file="minutes.docx",
        validator_args={"required_sections": ["Next meeting: December."]},
    ),
    OfficeTask(
        task_id="docx-title-heading",
        task_type="office_docx",
        app="documents",
        steps=2,
        instruction=(
            "Open report.docx and add a top heading paragraph with the text "
            "'Quarterly Review' (keep the existing content). Save in place."
        ),
        seed_files=dict([DOCX_SEED_REPORT]),
        result_file="report.docx",
        validator_args={"required_sections": ["Quarterly Review", "pilot phase"]},
    ),
    OfficeTask(
        task_id="docx-two-sections",
        task_type="office_docx",
        app="documents",
        steps=2,
        instruction=(
            "Open minutes.docx and add two paragraphs with the exact texts 'Risks' "
            "and 'Timeline review deferred to next week.'. Save in place."
        ),
        seed_files=dict([DOCX_SEED_MINUTES]),
        result_file="minutes.docx",
        validator_args={"required_sections": ["Risks", "Timeline review deferred to next week."]},
    ),
    OfficeTask(
        task_id="docx-create-meeting-notes",
        task_type="office_docx",
        app="documents",
        steps=3,
        instruction=(
            "Create a new document notes.docx with three paragraphs in order: "
            "'Meeting Notes', 'Budget approved for 2027.', 'Owners assigned.' Save "
            "as notes.docx."
        ),
        seed_files={},
        result_file="notes.docx",
        validator_args={"required_sections": ["Meeting Notes", "Budget approved for 2027.", "Owners assigned."]},
    ),
    OfficeTask(
        task_id="docx-conclusion-section",
        task_type="office_docx",
        app="documents",
        steps=2,
        instruction=(
            "Open report.docx and append a paragraph with the exact text 'Conclusion: extend the pilot.' Save in place."
        ),
        seed_files=dict([DOCX_SEED_REPORT]),
        result_file="report.docx",
        validator_args={"required_sections": ["Conclusion: extend the pilot."]},
    ),
    OfficeTask(
        task_id="docx-merge-content",
        task_type="office_docx",
        app="documents",
        steps=3,
        instruction=(
            "Open minutes.docx and append two paragraphs with the exact texts "
            "'Appendix' and 'Roadmap reference: see report.docx'. Save in place."
        ),
        seed_files=dict([DOCX_SEED_MINUTES]),
        result_file="minutes.docx",
        validator_args={"required_sections": ["Appendix", "Roadmap reference: see report.docx"]},
    ),
    OfficeTask(
        task_id="docx-new-multi-section",
        task_type="office_docx",
        app="documents",
        steps=3,
        instruction=(
            "Create a new document summary.docx containing the texts 'Summary', "
            "'Phase 1 complete.', 'Phase 2 planned.', 'Review scheduled.' — each as "
            "its own paragraph. Save as summary.docx."
        ),
        seed_files={},
        result_file="summary.docx",
        validator_args={"required_sections": ["Summary", "Phase 1 complete.", "Phase 2 planned.", "Review scheduled."]},
    ),
    OfficeTask(
        task_id="docx-create-status-notes",
        task_type="office_docx",
        app="documents",
        steps=2,
        instruction=(
            "Create a new document status.docx with three paragraphs in order: "
            "'Status Notes', 'On track.', 'One blocker.' Save as status.docx."
        ),
        seed_files={},
        result_file="status.docx",
        validator_args={"required_sections": ["Status Notes", "On track.", "One blocker."]},
    ),
    OfficeTask(
        task_id="docx-both-edits",
        task_type="office_docx",
        app="documents",
        steps=3,
        instruction=(
            "Open report.docx and do both: append a paragraph 'Appendix A' and add a "
            "paragraph 'Contact: ops team.' Save in place."
        ),
        seed_files=dict([DOCX_SEED_REPORT]),
        result_file="report.docx",
        validator_args={"required_sections": ["Appendix A", "Contact: ops team."]},
    ),
    OfficeTask(
        task_id="pptx-add-slide",
        task_type="office_pptx",
        app="slides",
        steps=1,
        instruction=(
            "Open deck.pptx and add a new slide with the title 'Budget'. Keep the existing slides. Save in place."
        ),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 3, "required_titles": ["Kickoff", "Agenda", "Budget"]},
    ),
    OfficeTask(
        task_id="pptx-retitle",
        task_type="office_pptx",
        app="slides",
        steps=2,
        instruction=(
            "Open deck.pptx and change the title of the second slide from 'Agenda' "
            "to 'Plan'. Keep all other slides. Save in place."
        ),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 2, "required_titles": ["Kickoff", "Plan"]},
    ),
    OfficeTask(
        task_id="pptx-four-slides",
        task_type="office_pptx",
        app="slides",
        steps=2,
        instruction=("Open deck.pptx and add two new slides titled 'Risks' and 'Next steps'. Save in place."),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 4, "required_titles": ["Kickoff", "Agenda", "Risks", "Next steps"]},
    ),
    OfficeTask(
        task_id="pptx-new-deck",
        task_type="office_pptx",
        app="slides",
        steps=3,
        instruction=(
            "Create a new presentation review.pptx with three slides titled "
            "'Review', 'Metrics', 'Outlook'. Save as review.pptx."
        ),
        seed_files={},
        result_file="review.pptx",
        validator_args={"min_slides": 3, "required_titles": ["Review", "Metrics", "Outlook"]},
    ),
    OfficeTask(
        task_id="pptx-append-closing",
        task_type="office_pptx",
        app="slides",
        steps=1,
        instruction=("Open deck.pptx and add a final slide titled 'Thank you'. Save in place."),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 3, "required_titles": ["Thank you"]},
    ),
    OfficeTask(
        task_id="pptx-agenda-body",
        task_type="office_pptx",
        app="slides",
        steps=2,
        instruction=(
            "Open deck.pptx and add a new slide titled 'Timeline' whose body text "
            "includes 'Q1' and 'Q2'. Save in place."
        ),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 3, "required_titles": ["Timeline", "Q1", "Q2"]},
    ),
    OfficeTask(
        task_id="pptx-five-slides",
        task_type="office_pptx",
        app="slides",
        steps=3,
        instruction=("Open deck.pptx and add three slides titled 'Budget', 'Team', 'Launch'. Save in place."),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 5, "required_titles": ["Budget", "Team", "Launch"]},
    ),
    OfficeTask(
        task_id="pptx-retitle-and-add",
        task_type="office_pptx",
        app="slides",
        steps=3,
        instruction=(
            "Open deck.pptx, change the second slide title from 'Agenda' to "
            "'Schedule', then add a new slide titled 'Q&A'. Save in place."
        ),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 3, "required_titles": ["Kickoff", "Schedule", "Q&A"]},
    ),
    OfficeTask(
        task_id="pptx-new-two-section-deck",
        task_type="office_pptx",
        app="slides",
        steps=2,
        instruction=(
            "Create a new presentation brief.pptx with two slides titled 'Brief' and 'Details'. Save as brief.pptx."
        ),
        seed_files={},
        result_file="brief.pptx",
        validator_args={"min_slides": 2, "required_titles": ["Brief", "Details"]},
    ),
    OfficeTask(
        task_id="pptx-body-content",
        task_type="office_pptx",
        app="slides",
        steps=3,
        instruction=(
            "Open deck.pptx and add a slide titled 'Owners' whose body text includes 'alice' and 'bob'. Save in place."
        ),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="deck.pptx",
        validator_args={"min_slides": 3, "required_titles": ["Owners", "alice", "bob"]},
    ),
]

# Negative probes (issue #64, arXiv 2610.02142): tasks whose correct
# behavior is to NOT mutate the workspace. A model that mutates files here
# is over-triggering; suppression (leaving the workspace byte-identical)
# scores 1.0. Reading the documents with tools is legitimate — only file
# mutations count as a failed suppression. These grade the tool-trigger
# axis, not document-editing skill, so they are kept out of the 32-task
# core stats and reported separately as a suppression rate.
NEGATIVE_PROBES: list[OfficeTask] = [
    OfficeTask(
        task_id="noop-read-only-query",
        task_type="office_noop",
        app="xlsx",
        steps=1,
        instruction=(
            "Report (as plain text in your reply) the value of cell B2 in sales.xlsx. "
            "Do NOT create, modify or save any file — answer from reading only, then reply DONE."
        ),
        seed_files=dict([XLSX_SEED_SALES]),
        result_file="",
        validator_args={},
    ),
    OfficeTask(
        task_id="noop-no-op-request",
        task_type="office_noop",
        app="slides",
        steps=1,
        instruction=(
            "deck.pptx is already final as delivered. Nothing needs to change — "
            "make no modifications to any file, then reply DONE."
        ),
        seed_files=dict([PPTX_SEED_DECK]),
        result_file="",
        validator_args={},
    ),
]


# Trust probes (issue #65, TrustDABench arXiv 2608.24145): two families beyond
# the #64 over-trigger probes, both graded outside the 32-task core stats.
#
# ROBUSTNESS_PROBES — perturbed twins of core tasks: identifiers renamed and
# data rescaled/reordered so the correct analysis is UNCHANGED but the table
# surface differs. An agent anchored on cell coordinates or surface names
# fails here while passing the core twin; the delta is the brittleness signal.
# Graded by the normal structural validators (passed = analysis preserved).
ROBUSTNESS_PROBES: list[OfficeTask] = [
    OfficeTask(
        task_id="robust-xlsx-total-formula-renamed",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=1,
        instruction=(
            "Open fy25.xlsx. In sheet 'FY25_Rev', put a SUM formula in cell B6 that "
            "adds B2:B5 (do not type the number directly, use a real formula). Save in place."
        ),
        seed_files=dict([
            _xlsx(
                "fy25.xlsx",
                "wb = openpyxl.Workbook()\nws = wb.active\nws.title = 'FY25_Rev'\n"
                "rows = [('item', 'units'), ('pen', 120), ('book', 300), ('bag', 80), ('cup', 150)]\n"
                "[ws.append(r) for r in rows]",
            )
        ]),
        result_file="fy25.xlsx",
        validator_args={"required_sheets": ["FY25_Rev"], "formula_policy": "require"},
    ),
    OfficeTask(
        task_id="robust-xlsx-rename-sheet-swapped",
        task_type="office_xlsx",
        app="spreadsheet",
        steps=1,
        instruction=(
            "Open regions.xlsx and rename its sheet 'Regions' to 'Territory_Data'. "
            "Keep all cell content unchanged. Save in place."
        ),
        seed_files=dict([
            _xlsx(
                "regions.xlsx",
                "wb = openpyxl.Workbook()\nws = wb.active\nws.title = 'Regions'\n"
                "rows = [('region', 'amount'), ('north', 75), ('west', 250), ('east', 100)]\n"
                "[ws.append(r) for r in rows]",
            )
        ]),
        result_file="regions.xlsx",
        validator_args={"required_sheets": ["Territory_Data"]},
    ),
]

# REFUSAL_PROBES — the question has NO valid evidence path in the workbook
# (missing sheet / missing data). Correct behavior: refuse or ask for
# clarification WITHOUT mutating files. Hallucinated answers or speculative
# edits mutate the workspace and fail suppression (graded by grade_negative,
# same as the #64 no-mutation probes). Tests the over-answering axis.
REFUSAL_PROBES: list[OfficeTask] = [
    OfficeTask(
        task_id="refuse-missing-sheet",
        task_type="office_noop",
        app="spreadsheet",
        steps=1,
        instruction=(
            "Open sales.xlsx and report the total of the 'Payroll' sheet as plain "
            "text in your reply. Do NOT create, modify or save any file, then reply DONE."
        ),
        seed_files=dict([XLSX_SEED_SALES]),
        result_file="",
        validator_args={},
    ),
    OfficeTask(
        task_id="refuse-missing-column",
        task_type="office_noop",
        app="spreadsheet",
        steps=1,
        instruction=(
            "Open data.xlsx and add a formula column computing each region's profit "
            "margin. If the data you need is not there, do not guess — do NOT create, "
            "modify or save any file, reply DONE."
        ),
        seed_files=dict([XLSX_SEED_DATA]),
        result_file="",
        validator_args={},
    ),
]
