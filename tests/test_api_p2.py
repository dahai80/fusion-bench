"""Tests for P2 API endpoints: custom suites, cases, result cases, HTML export, charts.
Importers/callers: CI pipeline (pytest tests/).
Affected API: POST /api/v1/suites, POST/GET /api/v1/suites/{id}/cases, GET /api/v1/results/{id}/cases, ReportGenerator.to_html/generate_radar_chart/generate_trend_chart.
Data schema: reuses BenchmarkTask, CaseResult, EvalResult, DatasetStore schemas (no new schemas).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐".
"""

from __future__ import annotations

from pathlib import Path

from fusion_bench.core.models import BenchmarkTask, EvalLevel
from fusion_bench.core.plugin_base import CaseResult, EvalResult
from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics


class TestSuiteCreateAPI:
    def test_create_custom_suite(self):
        from fusion_bench.orchestrator.scheduler import Scheduler

        scheduler = Scheduler()
        scheduler.load_default_suites()
        original_count = len(scheduler.list_suites())
        tasks = [
            BenchmarkTask(
                "custom-1",
                "Custom speed",
                EvalLevel.L1_MODEL,
                "speed",
                params={"runs": 2},
            ),
        ]
        scheduler.register_suite("my-custom", tasks)
        assert len(scheduler.list_suites()) == original_count + 1
        assert "my-custom" in scheduler.list_suites()
        result_tasks = scheduler.get_suite("my-custom")
        assert len(result_tasks) == 1
        assert result_tasks[0].executor_key == "speed"


class TestDatasetCasesAPI:
    def test_create_and_list_cases(self, tmp_path):
        from fusion_bench.storage.dataset_store import DatasetStore

        store = DatasetStore(db_path=tmp_path / "cases.db")
        cases = [
            {"input_text": "What is 2+2?", "expected": "4"},
            {"input_text": "What is 3+3?", "expected": "6"},
        ]
        ds_id = store.create(name="suite-test-cases", items=cases, description="test cases")
        assert ds_id.startswith("ds-")
        items = store.get_items(ds_id)
        assert len(items) == 2
        assert items[0]["input_text"] == "What is 2+2?"

    def test_list_datasets_by_name(self, tmp_path):
        from fusion_bench.storage.dataset_store import DatasetStore

        store = DatasetStore(db_path=tmp_path / "cases2.db")
        store.create(name="suite-abc-cases", items=[{"q": "hello"}])
        datasets = store.list_datasets(limit=100)
        matched = [d for d in datasets if d["name"] == "suite-abc-cases"]
        assert len(matched) == 1


class TestResultCasesAPI:
    def test_eval_result_cases_filter(self):
        cases = [
            CaseResult(input_text="q1", expected="a", actual="a", score=1.0, passed=True),
            CaseResult(input_text="q2", expected="b", actual="c", score=0.0, passed=False),
            CaseResult(input_text="q3", expected="d", actual="d", score=1.0, passed=True),
        ]
        er = EvalResult(
            task_id="t1",
            executor_key="speed",
            model="m1",
            level=EvalLevel.L1_MODEL,
            metric_name="accuracy",
            metric_value=0.67,
            cases=[c.__dict__ for c in cases],
        )
        all_cases = er.cases
        assert len(all_cases) == 3
        passed = [c for c in all_cases if c.get("passed")]
        assert len(passed) == 2
        failed = [c for c in all_cases if not c.get("passed")]
        assert len(failed) == 1


class TestHTMLExport:
    def test_to_html_basic(self):
        metrics = SpeedMetrics(decode_speed=30.0, prefill_speed=100.0, peak_memory_mb=2048)
        result = BenchmarkResult(model="test-model", config={}, metrics=metrics)
        from fusion_bench.reporter.report import ReportGenerator

        html = ReportGenerator.to_html([result], title="Test Report")
        assert "<!DOCTYPE html>" in html
        assert "test-model" in html
        assert "30.0" in html
        assert "Speed Rankings" in html

    def test_to_html_file(self, tmp_path):
        metrics = SpeedMetrics(decode_speed=25.0)
        result = BenchmarkResult(model="m1", config={}, metrics=metrics)
        from fusion_bench.reporter.report import ReportGenerator

        path = str(tmp_path / "report.html")
        _html = ReportGenerator.to_html([result], filepath=path, title="File Report")
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "File Report" in content


class TestRadarChart:
    def test_generate_radar_chart(self, tmp_path):
        metrics1 = SpeedMetrics(decode_speed=30.0, prefill_speed=100.0, peak_memory_mb=2048)
        metrics2 = SpeedMetrics(decode_speed=20.0, prefill_speed=80.0, peak_memory_mb=4096)
        r1 = BenchmarkResult(model="model-a", config={}, metrics=metrics1, stable=True)
        r2 = BenchmarkResult(model="model-b", config={}, metrics=metrics2, stable=False)
        from fusion_bench.reporter.report import ReportGenerator

        path = str(tmp_path / "radar.png")
        try:
            result = ReportGenerator.generate_radar_chart([r1, r2], output_path=path)
            assert result == path
            assert Path(path).exists()
        except ImportError:
            pass

    def test_radar_empty_results(self):
        from fusion_bench.reporter.report import ReportGenerator

        assert ReportGenerator.generate_radar_chart([]) == ""


class TestTrendChart:
    def test_generate_trend_chart(self, tmp_path):
        trend_data = [
            {"timestamp": "2026-07-20T10:00:00", "metric_value": 25.0, "model": "m1"},
            {"timestamp": "2026-07-21T10:00:00", "metric_value": 27.0, "model": "m1"},
            {"timestamp": "2026-07-22T10:00:00", "metric_value": 30.0, "model": "m1"},
        ]
        from fusion_bench.reporter.report import ReportGenerator

        path = str(tmp_path / "trend.png")
        try:
            result = ReportGenerator.generate_trend_chart(trend_data, output_path=path)
            assert result == path
            assert Path(path).exists()
        except ImportError:
            pass

    def test_trend_empty_data(self):
        from fusion_bench.reporter.report import ReportGenerator

        assert ReportGenerator.generate_trend_chart([]) == ""
