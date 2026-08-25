"""Tests for the `fusion-bench judge` CLI subcommand."""

from __future__ import annotations

import sys
from unittest.mock import patch

from fusion_bench import cli as cli_mod


def _run_cli(argv: list[str], tmp_path, monkeypatch):
    monkeypatch.setattr("fusion_bench.storage.judge_store._DEFAULT_DB_PATH", tmp_path / "judge.db")
    with patch.object(sys, "argv", ["fusion-bench", *argv]):
        return cli_mod.main()


class TestJudgeCLI:
    def test_create_then_list_then_show(self, tmp_path, monkeypatch, capsys):
        rc = _run_cli(
            ["judge", "create", "--name", "default", "--model", "qwen", "--type", "hybrid", "--weight", "0.6", "--criteria", "correctness,helpfulness"],
            tmp_path,
            monkeypatch,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "default" in out

        rc = _run_cli(["judge", "list"], tmp_path, monkeypatch)
        assert rc == 0
        out = capsys.readouterr().out
        assert "default" in out

        rc = _run_cli(["judge", "show", "--name", "default"], tmp_path, monkeypatch)
        assert rc == 0
        out = capsys.readouterr().out
        assert "qwen" in out
        assert "hybrid" in out

    def test_delete(self, tmp_path, monkeypatch, capsys):
        _run_cli(["judge", "create", "--name", "todelete", "--model", "m"], tmp_path, monkeypatch)
        capsys.readouterr()
        rc = _run_cli(["judge", "delete", "--name", "todelete"], tmp_path, monkeypatch)
        assert rc == 0
        out = capsys.readouterr().out
        assert "deleted" in out.lower()
        rc = _run_cli(["judge", "show", "--name", "todelete"], tmp_path, monkeypatch)
        # show of missing config should report not-found, not crash.
        assert rc == 0

    def test_create_defaults(self, tmp_path, monkeypatch, capsys):
        rc = _run_cli(["judge", "create", "--name", "d", "--model", "m"], tmp_path, monkeypatch)
        assert rc == 0
        out = capsys.readouterr().out
        assert "hybrid" in out  # default judge_type
