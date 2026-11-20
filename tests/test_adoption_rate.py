"""Issue #52 — adoption-rate metric script: exports, scanning, tiers (offline)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "adoption_rate.py"
spec = importlib.util.spec_from_file_location("adoption_rate", SCRIPT)
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)


@pytest.fixture()
def harness(tmp_path):
    pkg = tmp_path / "fusion_harness"
    pkg.mkdir()
    (pkg / "gadget.py").write_text("class Gadget:\n    pass\n\n\ndef run_gadget():\n    return 1\n", encoding="utf-8")
    (pkg / "__init__.py").write_text(
        "from fusion_harness.gadget import Gadget, run_gadget\n"
        "CONST = 1\n"
        '__all__ = ["Gadget", "run_gadget", "CONST"]\n',
        encoding="utf-8",
    )
    return tmp_path


def _consumer(tmp_path, name, files: dict[str, str]):
    root = tmp_path / name
    root.mkdir()
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return root


class TestCollectExports:
    def test_all_list(self, harness):
        assert ar.collect_exports(str(harness)) == ["CONST", "Gadget", "run_gadget"]

    def test_fallback_without_all(self, tmp_path):
        pkg = tmp_path / "fusion_harness"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("TOOLS = 1\n", encoding="utf-8")
        assert ar.collect_exports(str(tmp_path)) == ["TOOLS"]


class TestImportParsing:
    def test_root_imports(self):
        text = "from fusion_harness import A, B as bee\nfrom fusion_harness import (\n    C,\n    D,\n)\n"
        named, stars = ar.python_imported_names(text)
        assert named == {"A", "B", "C", "D"} and stars == set()

    def test_submodule_imports(self):
        text = "from fusion_harness.gadget import Gadget\nfrom fusion_harness.hooks import *  # noqa\n"
        named, stars = ar.python_imported_names(text)
        assert "Gadget" in named and stars == {"hooks"}

    def test_local_relative_import_ignored(self):
        named, stars = ar.python_imported_names("from .parse_repair import parse_model_json\n")
        assert not named and not stars


class TestCommentStripping:
    def test_comment_mention_not_attributed(self):
        text = "# fusion_harness.Gadget mentioned in a comment\nx = 1\n"
        assert "Gadget" not in ar.strip_python_comments(text)

    def test_real_code_survives(self):
        text = "from fusion_harness.gadget import Gadget  # note\nuse(Gadget)\n"
        assert "Gadget" in ar.strip_python_comments(text)


class TestScanConsumer:
    def test_attribute_and_import_union(self, harness, tmp_path):
        repo = _consumer(
            tmp_path,
            "as",
            {
                "server/x.py": "from fusion_harness import Gadget\n",
                "agent/y.py": "import fusion_harness\nfusion_harness.CONST\n",
                "agent/z.py": "from fusion_harness.gadget import *  # shim\n",
            },
        )
        consumed = ar.scan_consumer(str(repo), "as", ["Gadget", "run_gadget", "CONST"], str(harness))
        assert consumed == {"Gadget", "CONST", "run_gadget"}

    def test_tests_and_mutants_excluded(self, harness, tmp_path):
        repo = _consumer(
            tmp_path,
            "as",
            {
                "tests/t.py": "from fusion_harness import Gadget\n",
                "mutants/m.py": "from fusion_harness import Gadget\n",
                "src/ok.py": "pass\n",
            },
        )
        consumed = ar.scan_consumer(str(repo), "as", ["Gadget"], str(harness))
        assert consumed == set()


class TestConsoleMapping:
    def test_mapping_names_counted(self, harness):
        exports = ar.collect_exports(str(harness))
        assert ar.console_consumed(exports) == set()

    def test_stale_names_dropped(self, harness):
        exports = ["Gadget"]
        assert ar.console_consumed(exports) == set()


class TestMeasure:
    def test_tiers_and_rate(self, harness, tmp_path):
        repo = _consumer(tmp_path, "as", {"a.py": "from fusion_harness import Gadget\n"})
        exports = ar.collect_exports(str(harness))
        report = ar.measure(str(harness), [(str(repo), "as")], None, exports)
        assert report["total_exports"] == 3
        assert report["adopted"] == 1
        assert report["adoption_rate"] == 0.3333
        tiers = {r["name"]: r["tier"] for r in report["rows"]}
        assert tiers["Gadget"] == "A" and tiers["CONST"] == "B"
        assert report["zero_consumer_names"] == ["CONST", "run_gadget"]

    def test_console_consumer_counts(self, harness, tmp_path):
        exports = ["LLMFunnel", "Gadget"]
        report = ar.measure(str(harness), [], str(tmp_path), exports)
        tiers = {r["name"]: r["tier"] for r in report["rows"]}
        assert tiers["LLMFunnel"] == "A" and tiers["Gadget"] == "B"


class TestRender:
    def test_markdown_and_json_roundtrip(self, harness, tmp_path):
        repo = _consumer(tmp_path, "as", {"a.py": "from fusion_harness import Gadget\n"})
        exports = ar.collect_exports(str(harness))
        report = ar.measure(str(harness), [(str(repo), "as")], None, exports)
        md = ar.render_markdown(report)
        assert "adoption-rate snapshot" in md
        assert f"**Delivered rate: {report['delivered_rate']:.1%}**" in md
        assert f"(consumer-direct {report['adoption_rate']:.1%}" in md
        assert json.dumps(report)
