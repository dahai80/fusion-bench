"""Arabic/multilingual evaluation executor (issue #32, ai-speech-exam gap G9).

Benchmarks local-model Arabic capability across 5 dimensions:
1. translation_ar_en — model translates MSA→English, corpus BLEU + chrF vs references
2. translation_en_ar — model translates English→MSA, chrF primary (Arabic morphology
   makes token-BLEU brittle; BLEU still reported)
3. rtl_integrity — Arabic-prompt outputs checked for script preservation, mojibake
   (UTF-8-as-Latin1), legacy presentation forms, and U+FFFD
4. arabic_understanding — Arabic-language QA accuracy (normalized keyword containment)
5. stt_arabic — fusion-speech TTS→STT roundtrip WER; auto-skips when the speech
   service is unreachable (mirrors laya executor's 404 auto-skip)

Scoring uses sacrebleu (pure Python — no torch/transformers, per repo constraint).
COMET-style neural metrics need GPU model downloads and are out of scope here.

Routing (#31 convention): default base URL is the gateway (:11432) so bench traffic
is gateway-visible; direct fusion-mlx (:11434) is explicit opt-in (direct_mlx /
FUSION_BENCH_DIRECT_MLX=1), logged at construction, never a silent default.

Targets are provisional — no prior Arabic baseline exists in this repo; the first
real run establishes the baseline and targets should be re-tuned from it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any

import httpx
from fusion_core.config import client_key

from ..core.plugin_base import CaseResult, EvalResult, ExecutorPlugin, ExecutorType, TaskConfig

logger = logging.getLogger(__name__)

_DEFAULT_TESTSET_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "testsets"

# Routing defaults (issue #31 convention) — gateway is the traffic entry point.
_GATEWAY_BASE_URL = "http://localhost:11432/v1"
_DIRECT_MLX_BASE_URL = "http://localhost:11434/v1"

# fusion-speech daemon (STT/TTS) — STT dim auto-skips when unreachable.
_DEFAULT_SPEECH_URL = "http://localhost:11465"

# Provisional targets — first real run establishes the baseline (issue #32).
_SPEC_TARGETS = {
    "chrf_ar2en": 40.0,
    "chrf_en2ar": 35.0,
    "rtl_integrity": 0.90,
    "understanding_accuracy": 0.60,
    "stt_wer": 0.30,
}

# Arabic script block; presentation forms indicate legacy visual-order encoding.
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_PRESENTATION_FORMS_RE = re.compile(r"[ﭐ-﷿ﹰ-﻿]")
# UTF-8 Arabic mis-decoded as Latin-1/cp1252 shows these lead bytes.
_MOJIBAKE_RE = re.compile(r"[ØÙÂð\xef\xbf\xbd]")
# Arabic diacritics — stripped before keyword/answer comparison.
_DIACRITICS_RE = re.compile(r"[ً-ْٰـ]")


class ArabicEvalExecutor(ExecutorPlugin):
    name = "arabic"
    executor_type = ExecutorType.MODEL

    def __init__(
        self,
        mlx_base_url: str | None = None,
        api_key: str | None = None,
        direct_mlx: bool | None = None,
        speech_url: str | None = None,
    ):
        if direct_mlx is None:
            direct_mlx = os.environ.get("FUSION_BENCH_DIRECT_MLX", "").lower() in ("1", "true", "yes")
        if direct_mlx:
            base = (mlx_base_url or _DIRECT_MLX_BASE_URL).rstrip("/")
            logger.info(
                "Arabic executor: DIRECT fusion-mlx mode (%s) — bypasses gateway, measures raw engine capability",
                base,
            )
        else:
            base = (mlx_base_url or os.environ.get("FUSION_MLX_URL", _GATEWAY_BASE_URL)).rstrip("/")
            logger.info("Arabic executor: gateway mode (%s) — bench traffic routes through the gateway", base)
        self.mlx_base_url = base
        self.direct_mlx = direct_mlx or ":11434" in base
        # #35: single-point resolution in fusion-core (alias chain + profile semantics)
        self.api_key = api_key or client_key()
        self.speech_base_url = (speech_url or os.environ.get("FUSION_SPEECH_URL", _DEFAULT_SPEECH_URL)).rstrip("/")

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        model = config.model or ""
        testset_dir = Path(config.get("testset_dir") or _DEFAULT_TESTSET_DIR)
        cases: list[CaseResult] = []
        errors: list[str] = []
        dims: dict[str, Any] = {"mode": "direct-mlx" if self.direct_mlx else "gateway"}

        if not model:
            errors.append("no model specified — model dims skipped")
            dims["translation_ar_en"] = {"skipped": True, "reason": "no model"}
            dims["translation_en_ar"] = {"skipped": True, "reason": "no model"}
            dims["rtl_integrity"] = {"skipped": True, "reason": "no model"}
            dims["arabic_understanding"] = {"skipped": True, "reason": "no model"}
        else:
            trans_set = self._load_testset(testset_dir / "arabic_translation_30.json")
            ar2en = [t for t in trans_set if t.get("direction") == "ar2en"]
            en2ar = [t for t in trans_set if t.get("direction") == "en2ar"]
            dims["translation_ar_en"] = await self._bench_translation(model, ar2en, "ar2en", cases)
            dims["translation_en_ar"] = await self._bench_translation(model, en2ar, "en2ar", cases)

            rtl_set = self._load_testset(testset_dir / "arabic_rtl_20.json")
            if rtl_set:
                dims["rtl_integrity"] = await self._bench_rtl(model, rtl_set, cases)
            else:
                dims["rtl_integrity"] = {"skipped": True, "reason": "testset not found"}

            qa_set = self._load_testset(testset_dir / "arabic_qa_15.json")
            if qa_set:
                dims["arabic_understanding"] = await self._bench_understanding(model, qa_set, cases)
            else:
                dims["arabic_understanding"] = {"skipped": True, "reason": "testset not found"}

        stt_texts = self._load_testset(testset_dir / "arabic_translation_30.json")
        dims["stt_arabic"] = await self._bench_stt(stt_texts)

        composite = self._composite_score(dims)
        report_dir = Path(config.get("report_dir", "benchmarks/results/arabic-multilingual"))
        report_paths = self._write_report(dims, composite, report_dir, model)

        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=model,
            level="L4",
            metric_name="arabic_composite",
            metric_value=round(composite, 4),
            cases=cases,
            duration_seconds=time.time() - start,
            errors=errors,
            meta={
                "mode": "direct-mlx" if self.direct_mlx else "gateway",
                "dimensions": dims,
                "spec_targets": _SPEC_TARGETS,
                "report_files": report_paths,
            },
        )

    async def _chat(self, model: str, prompt: str, max_tokens: int = 256) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        async with httpx.AsyncClient(timeout=120.0, headers={"Authorization": f"Bearer {self.api_key}"}) as client:
            resp = await client.post(f"{self.mlx_base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            return ""

    async def _bench_translation(
        self, model: str, items: list[dict], direction: str, cases: list[CaseResult]
    ) -> dict[str, Any]:
        if not items:
            return {"skipped": True, "reason": "empty testset"}
        try:
            import sacrebleu
        except ImportError:
            logger.error("sacrebleu not installed — translation dims cannot score (pip install sacrebleu)")
            return {"skipped": True, "reason": "sacrebleu not installed"}

        src_key = "source"
        hypotheses: list[str] = []
        references: list[str] = []
        sources: list[str] = []
        for item in items:
            source = item.get(src_key, "")
            if direction == "ar2en":
                prompt = f"Translate the following Arabic sentence to English. Output only the translation.\n\n{source}"
            else:
                prompt = f"Translate the following English sentence to Modern Standard Arabic. Output only the translation.\n\n{source}"
            try:
                hyp = (await self._chat(model, prompt)).strip()
            except Exception as e:
                logger.warning("translation %s failed: %s", direction, e)
                hyp = ""
            ref = item.get("reference", "")
            hypotheses.append(hyp)
            references.append(ref)
            sources.append(source)
            cases.append(
                CaseResult(
                    input_text=source[:200],
                    expected=ref,
                    actual=hyp[:400],
                    score=1.0 if hyp else 0.0,
                    passed=bool(hyp),
                    meta={"dim": f"translation_{direction}"},
                )
            )

        bleu = sacrebleu.corpus_bleu(hypotheses, [references])
        chrf = sacrebleu.corpus_chrf(hypotheses, [references])
        # chrF word-F variant matches the original chrF paper default (beta=2).
        result = {
            "bleu": round(bleu.score, 2),
            "chrf": round(chrf.score, 2),
            "sample_count": len(items),
        }
        logger.info("Translation %s: BLEU=%.2f chrF=%.2f (n=%d)", direction, bleu.score, chrf.score, len(items))
        return result

    async def _bench_rtl(self, model: str, testset: list[dict], cases: list[CaseResult]) -> dict[str, Any]:
        passed = 0
        failure_kinds: dict[str, int] = {}
        for item in testset:
            prompt = item.get("prompt", "")
            try:
                out = await self._chat(model, prompt)
            except Exception as e:
                logger.warning("rtl bench item failed: %s", e)
                out = ""
            kind = self._rtl_check(out)
            if kind is None:
                passed += 1
            else:
                failure_kinds[kind] = failure_kinds.get(kind, 0) + 1
            cases.append(
                CaseResult(
                    input_text=prompt[:200],
                    expected="valid Arabic RTL text",
                    actual=out[:200],
                    score=1.0 if kind is None else 0.0,
                    passed=kind is None,
                    meta={"dim": "rtl_integrity", "failure": kind or ""},
                )
            )
        total = max(len(testset), 1)
        integrity = passed / total
        logger.info("RTL integrity: %.1f%% (%s)", integrity * 100, failure_kinds or "no failures")
        return {"integrity": round(integrity, 4), "failure_kinds": failure_kinds, "sample_count": len(testset)}

    async def _bench_understanding(self, model: str, testset: list[dict], cases: list[CaseResult]) -> dict[str, Any]:
        correct = 0
        for item in testset:
            question = item.get("question", "")
            keywords = [self._normalize_ar(k) for k in item.get("expected_keywords", [])]
            try:
                out = self._normalize_ar(await self._chat(model, question, max_tokens=128))
            except Exception as e:
                logger.warning("understanding item failed: %s", e)
                out = ""
            hit = any(k and k in out for k in keywords)
            if hit:
                correct += 1
            cases.append(
                CaseResult(
                    input_text=question[:200],
                    expected=" | ".join(item.get("expected_keywords", [])),
                    actual=out[:200],
                    score=1.0 if hit else 0.0,
                    passed=hit,
                    meta={"dim": "arabic_understanding"},
                )
            )
        total = max(len(testset), 1)
        accuracy = correct / total
        logger.info("Arabic understanding accuracy: %.1f%%", accuracy * 100)
        return {"accuracy": round(accuracy, 4), "sample_count": len(testset)}

    async def _bench_stt(self, testset: list[dict]) -> dict[str, Any]:
        # fusion-speech roundtrip: TTS the Arabic reference, STT it back, WER.
        # Auto-skips when the speech daemon is unreachable (mirrors laya 404 skip).
        available = await self._check_speech_endpoint()
        if not available:
            logger.info("fusion-speech not available; STT dim auto-skips.")
            return {"skipped": True, "reason": "fusion-speech unavailable"}
        texts = [t.get("reference", "") for t in testset if t.get("direction") == "en2ar"][:10]
        if not texts:
            return {"skipped": True, "reason": "no Arabic reference texts"}
        wers: list[float] = []
        for text in texts:
            try:
                audio = await self._tts(text)
                heard = await self._stt(audio)
                wers.append(self._wer(self._normalize_ar(text), self._normalize_ar(heard)))
            except Exception as e:
                logger.warning("STT roundtrip failed: %s", e)
        if not wers:
            return {"skipped": True, "reason": "all roundtrips failed"}
        wer = statistics.mean(wers)
        logger.info("Arabic STT roundtrip WER: %.3f (n=%d)", wer, len(wers))
        return {"wer": round(wer, 4), "sample_count": len(wers)}

    async def _check_speech_endpoint(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.speech_base_url}/health")
            return resp.status_code == 200
        except Exception as e:
            logger.debug("fusion-speech health check failed: %s", e)
            return False

    async def _tts(self, text: str) -> bytes:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.speech_base_url}/api/v1/tts", json={"text": text, "language": "ar"})
            resp.raise_for_status()
            return resp.content

    async def _stt(self, audio: bytes) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.speech_base_url}/api/v1/stt",
                files={"audio": ("speech.wav", audio, "audio/wav")},
                data={"language": "ar"},
            )
            resp.raise_for_status()
            return resp.json().get("text", "")

    @staticmethod
    def _rtl_check(text: str) -> str | None:
        # Returns None when the text passes; otherwise the failure kind.
        # Specific encodings diagnosed before the generic script check —
        # mojibake/presentation-form text contains no Arabic-block chars,
        # so the generic check would mask the real failure.
        if not text.strip():
            return "empty"
        if "�" in text:
            return "replacement_char"
        if _MOJIBAKE_RE.search(text):
            return "mojibake"
        if _PRESENTATION_FORMS_RE.search(text):
            return "presentation_forms"
        if not _ARABIC_RE.search(text):
            return "no_arabic_script"
        return None

    @staticmethod
    def _normalize_ar(text: str) -> str:
        text = _DIACRITICS_RE.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _wer(reference: str, hypothesis: str) -> float:
        ref_words = reference.split()
        hyp_words = hypothesis.split()
        if not ref_words:
            return 0.0 if not hyp_words else 1.0
        # Levenshtein on word lists
        prev = list(range(len(hyp_words) + 1))
        for i, rw in enumerate(ref_words, 1):
            cur = [i]
            for j, hw in enumerate(hyp_words, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
            prev = cur
        return prev[-1] / len(ref_words)

    def _composite_score(self, dims: dict[str, Any]) -> float:
        # Higher-is-better per dim: chrf/target capped at 1, integrity/accuracy direct,
        # STT inverted (wer target/actual capped at 1). Skipped dims drop out by weight.
        entries = []
        ar2en = dims.get("translation_ar_en", {})
        if not ar2en.get("skipped"):
            entries.append((0.15, min(ar2en.get("chrf", 0) / _SPEC_TARGETS["chrf_ar2en"], 1.0)))
        en2ar = dims.get("translation_en_ar", {})
        if not en2ar.get("skipped"):
            entries.append((0.15, min(en2ar.get("chrf", 0) / _SPEC_TARGETS["chrf_en2ar"], 1.0)))
        rtl = dims.get("rtl_integrity", {})
        if not rtl.get("skipped"):
            entries.append((0.30, min(rtl.get("integrity", 0) / _SPEC_TARGETS["rtl_integrity"], 1.0)))
        und = dims.get("arabic_understanding", {})
        if not und.get("skipped"):
            entries.append((0.25, min(und.get("accuracy", 0) / _SPEC_TARGETS["understanding_accuracy"], 1.0)))
        stt = dims.get("stt_arabic", {})
        if not stt.get("skipped"):
            wer = stt.get("wer", 1.0)
            entries.append((0.15, min(_SPEC_TARGETS["stt_wer"] / max(wer, 0.001), 1.0)))
        if not entries:
            return 0.0
        total_weight = sum(w for w, _ in entries)
        return sum(w * s for w, s in entries) / total_weight

    @staticmethod
    def _load_testset(path: Path) -> list[dict]:
        if not path.exists():
            logger.warning("Testset not found: %s", path)
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("Failed to load testset %s: %s", path, e)
            return []

    def _write_report(self, dims: dict[str, Any], composite: float, report_dir: Path, model: str) -> dict[str, str]:
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": model,
            "mode": "direct-mlx" if self.direct_mlx else "gateway",
            "endpoint": f"{self.mlx_base_url}/chat/completions",
            "composite_score": round(composite, 4),
            "dimensions": dims,
            "spec_targets": _SPEC_TARGETS,
            "notes": "Targets provisional — first Arabic baseline in this repo; re-tune from real runs.",
        }
        json_path = report_dir / "report.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        md_path = report_dir / "report.md"
        md_path.write_text(self._render_markdown_report(report), encoding="utf-8")
        logger.info("Arabic benchmark report written to %s", report_dir)
        return {"json": str(json_path), "markdown": str(md_path)}

    @staticmethod
    def _render_markdown_report(report: dict[str, Any]) -> str:
        dims = report.get("dimensions", {})
        targets = report.get("spec_targets", {})
        lines = [
            "# Arabic/Multilingual Evaluation Report (issue #32, ai-speech-exam G9)",
            "",
            f"**Timestamp**: {report.get('timestamp', 'N/A')}",
            f"**Model**: {report.get('model', 'N/A')}",
            f"**Mode**: {report.get('mode', 'N/A')}",
            f"**Endpoint**: {report.get('endpoint', 'N/A')}",
            f"**Composite Score**: {report.get('composite_score', 0):.4f}",
            "",
            "## Dimension Results (targets provisional — first baseline)",
            "",
            "| Dimension | Metric | Provisional Target | Actual | Status |",
            "|-----------|--------|--------------------|--------|--------|",
        ]
        ar2en = dims.get("translation_ar_en", {})
        if ar2en.get("skipped"):
            lines.append(
                f"| Translation AR→EN | chrF | ≥ {targets['chrf_ar2en']} | — | ⏭️ Skipped ({ar2en.get('reason', '')}) |"
            )
        else:
            v = ar2en.get("chrf", 0)
            lines.append(
                f"| Translation AR→EN | chrF | ≥ {targets['chrf_ar2en']} | {v} | {'✅' if v >= targets['chrf_ar2en'] else '❌'} |"
                + f" (BLEU {ar2en.get('bleu', 0)}, n={ar2en.get('sample_count', 0)}) |"
            )
        en2ar = dims.get("translation_en_ar", {})
        if en2ar.get("skipped"):
            lines.append(
                f"| Translation EN→AR | chrF | ≥ {targets['chrf_en2ar']} | — | ⏭️ Skipped ({en2ar.get('reason', '')}) |"
            )
        else:
            v = en2ar.get("chrf", 0)
            lines.append(
                f"| Translation EN→AR | chrF | ≥ {targets['chrf_en2ar']} | {v} | {'✅' if v >= targets['chrf_en2ar'] else '❌'} |"
                + f" (BLEU {en2ar.get('bleu', 0)}, n={en2ar.get('sample_count', 0)}) |"
            )
        rtl = dims.get("rtl_integrity", {})
        if rtl.get("skipped"):
            lines.append(f"| RTL Integrity | integrity | ≥ {targets['rtl_integrity'] * 100:.0f}% | — | ⏭️ Skipped |")
        else:
            v = rtl.get("integrity", 0)
            kinds = rtl.get("failure_kinds", {})
            kind_note = f" — failures: {kinds}" if kinds else ""
            lines.append(
                f"| RTL Integrity | integrity | ≥ {targets['rtl_integrity'] * 100:.0f}% | {v * 100:.1f}% |"
                f" {'✅' if v >= targets['rtl_integrity'] else '❌'}{kind_note} |"
            )
        und = dims.get("arabic_understanding", {})
        if und.get("skipped"):
            lines.append(
                f"| Arabic Understanding | accuracy | ≥ {targets['understanding_accuracy'] * 100:.0f}% | — | ⏭️ Skipped |"
            )
        else:
            v = und.get("accuracy", 0)
            lines.append(
                f"| Arabic Understanding | accuracy | ≥ {targets['understanding_accuracy'] * 100:.0f}% |"
                f" {v * 100:.1f}% | {'✅' if v >= targets['understanding_accuracy'] else '❌'} |"
            )
        stt = dims.get("stt_arabic", {})
        if stt.get("skipped"):
            lines.append(
                f"| Arabic STT (roundtrip) | WER | ≤ {targets['stt_wer']} | — | ⏭️ Skipped ({stt.get('reason', '')}) |"
            )
        else:
            v = stt.get("wer", 1.0)
            lines.append(
                f"| Arabic STT (roundtrip) | WER | ≤ {targets['stt_wer']} | {v} | {'✅' if v <= targets['stt_wer'] else '❌'} |"
            )
        lines += [
            "",
            "## Notes",
            "",
            "- Scoring: sacrebleu corpus BLEU + chrF (no torch/transformers — repo constraint).",
            "- COMET-style neural metrics need model downloads; out of scope for this executor.",
            "- RTL integrity checks: Arabic script present, no mojibake (UTF-8-as-Latin1),",
            "  no legacy presentation forms (visual-order encoding), no U+FFFD.",
            "- STT dim: fusion-speech TTS→STT roundtrip; auto-skips when the daemon is down",
            "  (fusion-speech not running at benchmark time).",
            "- Test sets committed to `benchmarks/testsets/` (hand-authored MSA).",
        ]
        return "\n".join(lines)

    def is_available(self) -> bool:
        try:
            import sacrebleu  # noqa: F401

            return True
        except ImportError:
            logger.warning("Arabic executor requires 'sacrebleu' package")
            return False
