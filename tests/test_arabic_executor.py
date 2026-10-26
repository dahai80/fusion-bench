"""Tests for ArabicEvalExecutor (#32, ai-speech-exam gap G9)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fusion_bench.core.plugin_base import ExecutorType, TaskConfig
from fusion_bench.executors.arabic_executor import _DEFAULT_TESTSET_DIR, ArabicEvalExecutor

_AR_SENTENCE = "الطالب يدرس اللغة العربية في الجامعة."


def _chat_responder(prompt: str, source_map: dict[str, str]) -> str:
    for src, resp in source_map.items():
        if src in prompt:
            return resp
    return _AR_SENTENCE


def _make_executor(
    monkeypatch,
    source_map: dict[str, str] | None = None,
    speech_available: bool = False,
    stt_echo: bool = True,
):
    executor = ArabicEvalExecutor(mlx_base_url="http://localhost:11434/v1", api_key="test-key")
    source_map = source_map or {}

    async def fake_post(self, url, json=None, **kw):
        req = httpx.Request("POST", url)
        if "/chat/completions" in url:
            prompt = json["messages"][0]["content"]
            return httpx.Response(
                200, request=req, json={"choices": [{"message": {"content": _chat_responder(prompt, source_map)}}]}
            )
        if "/api/v1/tts" in url:
            return httpx.Response(200, request=req, content=b"fake-audio")
        if "/api/v1/stt" in url:
            return httpx.Response(200, request=req, json={"text": "صباح الخير" if stt_echo else "garbage"})
        return httpx.Response(404, request=req)

    async def fake_get(self, url, **kw):
        req = httpx.Request("GET", url)
        if "/health" in url:
            if speech_available:
                return httpx.Response(200, request=req)
            return httpx.Response(503, request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return executor


def _write_testsets(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    trans = [
        {"direction": "ar2en", "source": "مرحبا", "reference": "Hello"},
        {"direction": "en2ar", "source": "Good morning", "reference": "صباح الخير"},
    ]
    rtl = [{"prompt": "اكتب جملة عن التعليم."}]
    qa = [
        {"question": "ما هي عاصمة مصر؟", "expected_keywords": ["القاهرة"]},
        {"question": "كم عدد أيام الأسبوع؟", "expected_keywords": ["سبعة", "7"]},
    ]
    (tmp_path / "arabic_translation_30.json").write_text(json.dumps(trans, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "arabic_rtl_20.json").write_text(json.dumps(rtl, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "arabic_qa_15.json").write_text(json.dumps(qa, ensure_ascii=False), encoding="utf-8")
    return tmp_path


class TestRegistration:
    def test_executor_type(self):
        assert ArabicEvalExecutor.executor_type == ExecutorType.MODEL

    def test_name(self):
        assert ArabicEvalExecutor.name == "arabic"

    def test_is_available(self):
        assert ArabicEvalExecutor().is_available()


class TestRTLCheck:
    def test_valid_arabic_passes(self):
        assert ArabicEvalExecutor._rtl_check(_AR_SENTENCE) is None

    def test_empty_fails(self):
        assert ArabicEvalExecutor._rtl_check("   ") == "empty"

    def test_no_arabic_script_fails(self):
        assert ArabicEvalExecutor._rtl_check("hello world") == "no_arabic_script"

    def test_replacement_char_fails(self):
        assert ArabicEvalExecutor._rtl_check("القاهرة �") == "replacement_char"

    def test_mojibake_fails(self):
        # UTF-8 Arabic mis-decoded as Latin-1
        assert ArabicEvalExecutor._rtl_check("Ø§Ù„Ù‚Ø§Ù‡Ø±Ø©") == "mojibake"

    def test_presentation_forms_fail(self):
        assert ArabicEvalExecutor._rtl_check("ﺍﻟﻘﺎﻫﺮﺓ") == "presentation_forms"


class TestNormalize:
    def test_strips_diacritics(self):
        assert ArabicEvalExecutor._normalize_ar("مُحَمَّد") == "محمد"

    def test_collapses_whitespace(self):
        assert ArabicEvalExecutor._normalize_ar("  القاهرة   جميلة  ") == "القاهرة جميلة"


class TestWER:
    def test_perfect(self):
        assert ArabicEvalExecutor._wer("a b c", "a b c") == 0.0

    def test_substitution(self):
        assert ArabicEvalExecutor._wer("a b c", "a x c") == pytest.approx(1 / 3)

    def test_empty_reference(self):
        assert ArabicEvalExecutor._wer("", "a b") == 1.0

    def test_empty_hypothesis(self):
        assert ArabicEvalExecutor._wer("a b", "") == 1.0


class TestRouting:
    # issue #31 convention: gateway default; direct fusion-mlx explicit opt-in.

    def test_default_is_gateway(self, monkeypatch):
        monkeypatch.delenv("FUSION_MLX_URL", raising=False)
        monkeypatch.delenv("FUSION_BENCH_DIRECT_MLX", raising=False)
        executor = ArabicEvalExecutor()
        assert executor.mlx_base_url == "http://localhost:11432/v1"
        assert executor.direct_mlx is False

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.delenv("FUSION_BENCH_DIRECT_MLX", raising=False)
        monkeypatch.setenv("FUSION_MLX_URL", "http://gw.example:11432/v1")
        executor = ArabicEvalExecutor()
        assert executor.mlx_base_url == "http://gw.example:11432/v1"

    def test_direct_flag_opt_in(self, monkeypatch):
        monkeypatch.delenv("FUSION_MLX_URL", raising=False)
        executor = ArabicEvalExecutor(direct_mlx=True)
        assert executor.mlx_base_url == "http://localhost:11434/v1"
        assert executor.direct_mlx is True

    def test_direct_env_opt_in(self, monkeypatch):
        monkeypatch.delenv("FUSION_MLX_URL", raising=False)
        monkeypatch.setenv("FUSION_BENCH_DIRECT_MLX", "1")
        executor = ArabicEvalExecutor()
        assert executor.direct_mlx is True

    def test_explicit_11434_url_inferred_direct(self):
        executor = ArabicEvalExecutor(mlx_base_url="http://localhost:11434/v1")
        assert executor.direct_mlx is True


class TestCommittedTestsets:
    def test_translation_testset(self):
        items = ArabicEvalExecutor._load_testset(_DEFAULT_TESTSET_DIR / "arabic_translation_30.json")
        assert len(items) == 30
        assert sum(1 for t in items if t["direction"] == "ar2en") == 15
        assert sum(1 for t in items if t["direction"] == "en2ar") == 15

    def test_rtl_testset(self):
        items = ArabicEvalExecutor._load_testset(_DEFAULT_TESTSET_DIR / "arabic_rtl_20.json")
        assert len(items) == 20
        assert all("prompt" in i for i in items)

    def test_qa_testset(self):
        items = ArabicEvalExecutor._load_testset(_DEFAULT_TESTSET_DIR / "arabic_qa_15.json")
        assert len(items) == 15
        assert all("expected_keywords" in i for i in items)


class TestRun:
    async def test_run_all_model_dims(self, monkeypatch, tmp_path):
        source_map = {
            "مرحبا": "Hello",
            "Good morning": "صباح الخير",
            "عاصمة مصر": "القاهرة",
            "أيام الأسبوع": "سبعة",
        }
        executor = _make_executor(monkeypatch, source_map=source_map)
        testset_dir = _write_testsets(tmp_path / "sets")
        config = TaskConfig(
            task_id="arabic-test",
            model="test-model",
            executor_key="arabic",
            params={"testset_dir": str(testset_dir), "report_dir": str(tmp_path / "report")},
        )
        result = await executor.run(config)
        assert result.executor_key == "arabic"
        assert result.level == "L4"
        dims = result.meta["dimensions"]
        assert dims["translation_ar_en"]["chrf"] > 0
        assert dims["translation_en_ar"]["chrf"] > 0
        assert dims["rtl_integrity"]["integrity"] == 1.0
        assert dims["arabic_understanding"]["accuracy"] == 1.0
        assert dims["stt_arabic"].get("skipped") is True
        assert result.metric_value > 0

    async def test_mode_in_meta_and_report(self, monkeypatch, tmp_path):
        executor = _make_executor(monkeypatch)
        testset_dir = _write_testsets(tmp_path / "sets")
        config = TaskConfig(
            task_id="arabic-mode",
            model="test-model",
            executor_key="arabic",
            params={"testset_dir": str(testset_dir), "report_dir": str(tmp_path / "report")},
        )
        result = await executor.run(config)
        assert result.meta["mode"] == "direct-mlx"
        report = json.loads(Path(result.meta["report_files"]["json"]).read_text(encoding="utf-8"))
        assert report["mode"] == "direct-mlx"

    async def test_no_model_skips_model_dims(self, monkeypatch, tmp_path):
        executor = _make_executor(monkeypatch)
        config = TaskConfig(
            task_id="arabic-nomodel",
            model="",
            executor_key="arabic",
            params={"report_dir": str(tmp_path)},
        )
        result = await executor.run(config)
        dims = result.meta["dimensions"]
        assert dims["translation_ar_en"].get("skipped") is True
        assert dims["rtl_integrity"].get("skipped") is True
        assert dims["arabic_understanding"].get("skipped") is True
        assert result.errors

    async def test_report_written(self, monkeypatch, tmp_path):
        executor = _make_executor(monkeypatch)
        config = TaskConfig(
            task_id="arabic-report", model="", executor_key="arabic", params={"report_dir": str(tmp_path)}
        )
        result = await executor.run(config)
        report_files = result.meta["report_files"]
        assert Path(report_files["json"]).exists()
        md = Path(report_files["markdown"]).read_text(encoding="utf-8")
        assert "Arabic/Multilingual Evaluation Report" in md
        assert "Skipped" in md


class TestSTT:
    async def test_unavailable_auto_skips(self, monkeypatch):
        executor = _make_executor(monkeypatch, speech_available=False)
        result = await executor._bench_stt([{"direction": "en2ar", "reference": "صباح الخير"}])
        assert result.get("skipped") is True
        assert "unavailable" in result.get("reason", "")

    async def test_roundtrip_wer(self, monkeypatch):
        executor = _make_executor(monkeypatch, speech_available=True, stt_echo=True)

        # Patch _stt to echo the exact reference so WER = 0 deterministically.
        async def fake_stt(audio: bytes) -> str:
            return executor._current_tts_text

        executor._current_tts_text = ""
        orig_tts = executor._tts

        async def tracked_tts(text: str) -> bytes:
            executor._current_tts_text = text
            return await orig_tts(text)

        executor._tts = tracked_tts
        executor._stt = fake_stt
        result = await executor._bench_stt([{"direction": "en2ar", "reference": "صباح الخير"}])
        assert result.get("wer") == 0.0
        assert result["sample_count"] == 1


class TestComposite:
    def test_all_skipped_zero(self):
        executor = ArabicEvalExecutor()
        dims = {
            "translation_ar_en": {"skipped": True},
            "translation_en_ar": {"skipped": True},
            "rtl_integrity": {"skipped": True},
            "arabic_understanding": {"skipped": True},
            "stt_arabic": {"skipped": True},
        }
        assert executor._composite_score(dims) == 0.0

    def test_active_dims_normalize_by_weight(self):
        executor = ArabicEvalExecutor()
        dims = {
            "translation_ar_en": {"chrf": 40.0},
            "translation_en_ar": {"chrf": 35.0},
            "rtl_integrity": {"integrity": 0.9},
            "arabic_understanding": {"accuracy": 0.6},
            "stt_arabic": {"skipped": True},
        }
        # All active dims exactly at target → composite 1.0
        assert executor._composite_score(dims) == pytest.approx(1.0)

    def test_stt_inverted(self):
        executor = ArabicEvalExecutor()
        dims = {
            "translation_ar_en": {"skipped": True},
            "translation_en_ar": {"skipped": True},
            "rtl_integrity": {"skipped": True},
            "arabic_understanding": {"skipped": True},
            "stt_arabic": {"wer": 0.15},
        }
        # WER below target → capped at 1.0
        assert executor._composite_score(dims) == pytest.approx(1.0)


class TestSuiteRegistration:
    def test_arabic_suite_registered(self):
        from fusion_bench.orchestrator.scheduler import Scheduler

        scheduler = Scheduler()
        scheduler.load_default_suites()
        assert "arabic-multilingual" in scheduler.list_suites()
        tasks = scheduler.get_suite("arabic-multilingual")
        assert tasks[0].executor_key == "arabic"
