"""Durability benchmark tests (issue #70). Deterministic, no live services."""

from __future__ import annotations

import json
import sqlite3

import pytest

from fusion_bench.durability import (
    build_report,
    compute_metrics,
    load_cowork_audits,
    load_cowork_scheduled,
    load_supervisor_runs,
    render_markdown,
    verify_report,
    write_report,
)


def _make_db(tmp_path, runs):
    db = tmp_path / "fsb_data.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (runId TEXT PRIMARY KEY, wsId TEXT NOT NULL, wfId TEXT NOT NULL, data TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE run_traces (traceId TEXT PRIMARY KEY, runId TEXT NOT NULL, nodeId TEXT NOT NULL, seq INTEGER NOT NULL, data TEXT NOT NULL)"
    )
    for run, traces in runs:
        conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (run["runId"], "ws", "wf", json.dumps(run)))
        for i, t in enumerate(traces):
            conn.execute(
                "INSERT INTO run_traces VALUES (?, ?, ?, ?, ?)",
                (f"t{run['runId']}{i}", run["runId"], t["node_id"], i, json.dumps(t)),
            )
    conn.commit()
    conn.close()
    return db


def _run(run_id, status, start, end):
    return {
        "runId": run_id,
        "workspaceId": "ws",
        "workflowId": "wf",
        "status": status,
        "startTime": start,
        "endTime": end,
    }


def _trace(node, status):
    return {
        "node_id": node,
        "status": status,
        "enterTime": "2026-11-28T01:00:00.000000Z",
        "exitTime": "2026-11-28T01:00:01.000000Z",
    }


class TestIngest:
    def test_load_supervisor_runs(self, tmp_path):
        db = _make_db(
            tmp_path,
            [
                (_run("r1", "COMPLETED", "2026-11-28T01:00:00Z", "2026-11-28T02:30:00Z"), [_trace("n1", "success")]),
                (_run("r2", "FAILED", "2026-11-28T03:00:00Z", "2026-11-28T03:10:00Z"), [_trace("n1", "failed")]),
            ],
        )
        runs = load_supervisor_runs(db)
        assert len(runs) == 2
        assert runs[0]["status"] == "COMPLETED"
        assert runs[0]["node_traces"][0]["status"] == "success"
        assert runs[1]["node_traces"][0]["status"] == "failed"

    def test_load_cowork_audits_chain(self, tmp_path):
        assets = tmp_path / "assets" / "wf_x"
        assets.mkdir(parents=True)
        rows = [
            {"at": 1, "digest": "a", "prev_digest": "", "status": "active"},
            {"at": 2, "digest": "b", "prev_digest": "a", "status": "active"},
            {"at": 3, "digest": "c", "prev_digest": "zz", "status": "active"},
        ]
        (assets / "audit.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        trails = load_cowork_audits(assets.parent)
        assert len(trails) == 1
        assert [r["digest"] for r in trails[0]["revisions"]] == ["a", "b", "c"]

    def test_load_cowork_scheduled(self, tmp_path):
        p = tmp_path / "scheduled_tasks.json"
        p.write_text(
            json.dumps(
                [
                    {"run_count": 3, "fail_count": 1, "status": "active"},
                    {"run_count": 2, "fail_count": 0, "status": "paused"},
                ]
            )
        )
        stats = load_cowork_scheduled(p)
        assert stats == {"task_count": 2, "active_count": 1, "total_runs": 5, "total_failures": 1}


class TestMetrics:
    def test_survival_and_recovery(self):
        runs = [
            {"run_id": "r1", "status": "COMPLETED", "started_at": "", "ended_at": "", "node_traces": []},
            {
                "run_id": "r2",
                "status": "FAILED",
                "started_at": "",
                "ended_at": "",
                "node_traces": [_trace("n", "failed")],
            },
            {
                "run_id": "r3",
                "status": "COMPLETED",
                "started_at": "",
                "ended_at": "",
                "node_traces": [_trace("n", "failed"), _trace("n2", "success")],
            },
        ]
        m = compute_metrics(runs, [], {})
        assert m["long_task_survival_rate"]["num"] == 2
        assert m["long_task_survival_rate"]["den"] == 3
        assert m["failure_recovery_rate"]["num"] == 1
        assert m["failure_recovery_rate"]["den"] == 2
        assert not m["long_task_survival_rate"]["sufficient"]

    def test_checkpoint_chain_intact_and_broken(self):
        audits = [
            {
                "workflow_id": "wf",
                "revisions": [
                    {"at": 1, "digest": "a", "prev_digest": "", "status": "s"},
                    {"at": 2, "digest": "b", "prev_digest": "a", "status": "s"},
                    {"at": 3, "digest": "c", "prev_digest": "b", "status": "s"},
                ],
            },
            {
                "workflow_id": "wf2",
                "revisions": [
                    {"at": 1, "digest": "x", "prev_digest": "", "status": "s"},
                    {"at": 2, "digest": "y", "prev_digest": "broken", "status": "s"},
                ],
            },
        ]
        m = compute_metrics([], audits, {})
        assert m["checkpoint_restore_correctness"]["num"] == 2
        assert m["checkpoint_restore_correctness"]["den"] == 3

    def test_hours_scale_ratio(self):
        runs = [
            {
                "run_id": "r1",
                "status": "COMPLETED",
                "started_at": "2026-11-28T01:00:00Z",
                "ended_at": "2026-11-28T03:00:00Z",
                "node_traces": [],
            },
            {
                "run_id": "r2",
                "status": "FAILED",
                "started_at": "2026-11-28T01:00:00Z",
                "ended_at": "2026-11-28T02:30:00Z",
                "node_traces": [],
            },
            {
                "run_id": "r3",
                "status": "COMPLETED",
                "started_at": "2026-11-28T01:00:00Z",
                "ended_at": "2026-11-28T01:30:00Z",
                "node_traces": [],
            },
        ]
        m = compute_metrics(runs, [], {})
        assert m["hours_scale_completion_ratio"]["num"] == 1
        assert m["hours_scale_completion_ratio"]["den"] == 2

    def test_insufficient_metrics_are_none(self):
        m = compute_metrics([], [], {})
        for key in (
            "long_task_survival_rate",
            "failure_recovery_rate",
            "checkpoint_restore_correctness",
            "hours_scale_completion_ratio",
        ):
            assert m[key]["value"] is None
            assert not m[key]["sufficient"]


class TestReport:
    def _dataset(self):
        audits = [
            {
                "workflow_id": "wf",
                "revisions": [
                    {"at": 1, "digest": "a", "prev_digest": "", "status": "s"},
                    {"at": 2, "digest": "b", "prev_digest": "a", "status": "s"},
                ],
            }
        ]
        runs = [
            {
                "run_id": "r1",
                "status": "COMPLETED",
                "started_at": "2026-11-28T01:00:00Z",
                "ended_at": "2026-11-28T02:00:00Z",
                "node_traces": [],
            },
        ]
        scheduled = {"task_count": 9, "active_count": 2, "total_runs": 5, "total_failures": 0}
        return runs, audits, scheduled

    def test_build_verify_roundtrip(self):
        runs, audits, scheduled = self._dataset()
        report = build_report(runs, audits, scheduled)
        dataset = {"supervisor_runs": runs, "cowork_audits": audits, "scheduled_task_stats": scheduled}
        ok, drifts = verify_report(dataset, report)
        assert ok
        assert drifts == []

    def test_verify_detects_drift(self):
        runs, audits, scheduled = self._dataset()
        report = build_report(runs, audits, scheduled)
        report["metrics"]["checkpoint_restore_correctness"]["num"] = 99
        dataset = {"supervisor_runs": runs, "cowork_audits": audits, "scheduled_task_stats": scheduled}
        ok, drifts = verify_report(dataset, report)
        assert not ok
        assert any("checkpoint_restore_correctness.num" in d for d in drifts)

    def test_render_markdown_marks_insufficient(self):
        runs, audits, scheduled = self._dataset()
        report = build_report(runs, audits, scheduled)
        md = render_markdown(report)
        assert "insufficient" in md
        assert "long_task_survival_rate" in md

    def test_write_report(self, tmp_path):
        runs, audits, scheduled = self._dataset()
        report = build_report(runs, audits, scheduled)
        write_report(report, tmp_path)
        assert (tmp_path / "durability-report.json").is_file()
        assert (tmp_path / "durability-report.md").is_file()

    def test_committed_dataset_reproduces_committed_report(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        dataset_path = root / "bench" / "durability" / "dataset-v1.json"
        report_path = root / "bench" / "durability" / "durability-report.json"
        if not dataset_path.is_file():
            pytest.skip("committed durability dataset not present")
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        ok, drifts = verify_report(dataset, report)
        assert ok, drifts
