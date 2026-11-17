"""Offline, bounded NLI adapter for claim-to-evidence assessment.

The model is loaded only when explicitly selected. It uses a pre-downloaded,
quantized ONNX model and CPU inference so the verifier does not require a
hosted LLM/API. NLI scores measure textual entailment, not factual truth.
"""
from __future__ import annotations

import json
import math
import os
from contextlib import contextmanager
from local_model_lifecycle import workload
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
DEFAULT_THRESHOLD = 0.80
MAX_PAIRS_PER_RUN = 48
MAX_SEQUENCE_LENGTH = 512

_MODEL_CACHE: dict[str, "LocalNLIModel"] = {}


class LocalNLIError(RuntimeError):
    """Raised when the optional local NLI runtime is unavailable or invalid."""


def _softmax(values: list[float]) -> list[float]:
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise LocalNLIError("NLI model must return three finite logits")
    maximum = max(values)
    exps = [math.exp(value - maximum) for value in values]
    total = sum(exps)
    if not total:
        raise LocalNLIError("NLI model returned invalid logits")
    return [value / total for value in exps]


def _label_indices(config: Mapping[str, Any]) -> dict[str, int]:
    raw = config.get("id2label")
    if not isinstance(raw, Mapping):
        raise LocalNLIError("NLI config is missing id2label")
    labels: dict[str, int] = {}
    for index, label in raw.items():
        try:
            position = int(index)
        except (TypeError, ValueError):
            continue
        normalized = str(label).strip().casefold()
        if "entail" in normalized:
            labels["entailment"] = position
        elif "contrad" in normalized:
            labels["contradiction"] = position
        elif "neutral" in normalized:
            labels["neutral"] = position
    if set(labels) != {"entailment", "contradiction", "neutral"} or set(labels.values()) != {0, 1, 2}:
        raise LocalNLIError("NLI config does not expose the three expected labels")
    return labels


class LocalNLIModel:
    """Lazy ONNX Runtime wrapper; pair inference is sequential and CPU-only."""

    def __init__(self, model_dir: str) -> None:
        directory = Path(model_dir).expanduser().resolve()
        config_path = directory / "config.json"
        model_path = directory / "onnx" / "model_quantized.onnx"
        if not config_path.is_file() or not model_path.is_file():
            raise LocalNLIError(
                "Local NLI model files are missing; run scripts/download_local_nli_model.py first"
            )
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise LocalNLIError(
                "Install the optional local runtime from requirements-local-ai.txt"
            ) from exc

        try:
            ort.disable_telemetry_events()
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.labels = _label_indices(config)
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(directory), local_files_only=True
            )
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            self.input_names = {item.name for item in self.session.get_inputs()}
        except Exception as exc:
            raise LocalNLIError("Could not initialize the local NLI model") from exc

    def score(self, premise: str, hypothesis: str) -> dict[str, float]:
        import numpy as np

        try:
            encoded = self.tokenizer(
                premise,
                hypothesis,
                return_tensors="np",
                truncation=True,
                max_length=MAX_SEQUENCE_LENGTH,
            )
            feed = {
                name: np.asarray(value, dtype=np.int64)
                for name, value in encoded.items()
                if name in self.input_names
            }
            outputs = self.session.run(None, feed)
            logits = np.asarray(outputs[0], dtype=np.float64).reshape(-1).tolist()
            probabilities = _softmax(logits)
            return {
                label: float(probabilities[index])
                for label, index in self.labels.items()
            }
        except LocalNLIError:
            raise
        except Exception as exc:
            raise LocalNLIError("Local NLI inference failed") from exc


def _model() -> LocalNLIModel:
    model_dir = os.environ.get("ORACLE_NLI_MODEL_DIR", "").strip()
    if not model_dir:
        raise LocalNLIError("ORACLE_NLI_MODEL_DIR is required for local NLI")
    key = str(Path(model_dir).expanduser().resolve())
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = LocalNLIModel(key)
    return _MODEL_CACHE[key]


def _threshold() -> float:
    raw = os.environ.get("ORACLE_NLI_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise LocalNLIError("ORACLE_NLI_THRESHOLD must be numeric") from exc
    if not 0.50 <= value <= 0.99:
        raise LocalNLIError("ORACLE_NLI_THRESHOLD must be between 0.50 and 0.99")
    return value


def _judge_payload(payload: dict[str, Any]) -> str:
    """Return the existing semantic_verifier JSON contract using local NLI."""
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise LocalNLIError("NLI payload claims must be a list")
    model: LocalNLIModel | None = None
    threshold = _threshold()
    pair_count = 0
    results = []

    for claim in claims:
        if not isinstance(claim, Mapping):
            continue
        claim_id = claim.get("claim_id")
        claim_text = claim.get("claim")
        if not isinstance(claim_id, str) or not isinstance(claim_text, str):
            continue
        evidence = claim.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []

        supported: list[str] = []
        contradicted: list[str] = []
        top_support = 0.0
        top_contradiction = 0.0
        exhausted = pair_count >= MAX_PAIRS_PER_RUN
        for item in evidence:
            if exhausted:
                break
            if not isinstance(item, Mapping):
                continue
            # A local NLI score on snippets is not enough for a decisive label.
            if item.get("evidence_level") != "extracted_page":
                continue
            source_id = item.get("source_id")
            excerpt = item.get("excerpt")
            if not isinstance(source_id, str) or not isinstance(excerpt, str) or not excerpt.strip():
                continue
            if pair_count >= MAX_PAIRS_PER_RUN:
                exhausted = True
                break
            if model is None:
                model = _model()
            pair_count += 1
            scores = model.score(excerpt[:7000], claim_text[:700])
            entailment = scores.get("entailment", 0.0)
            contradiction = scores.get("contradiction", 0.0)
            top_support = max(top_support, entailment)
            top_contradiction = max(top_contradiction, contradiction)
            if entailment >= threshold:
                supported.append(source_id)
            if contradiction >= threshold:
                contradicted.append(source_id)

        if exhausted:
            # A truncated comparison set must never be presented as a complete verdict.
            status = "UNVERIFIED"
            supported = []
            contradicted = []
        elif supported and contradicted:
            status = "CONFLICTING_EVIDENCE"
        elif supported:
            status = "SUPPORTED"
        elif contradicted:
            status = "CONTRADICTED"
        else:
            status = "INSUFFICIENT_EVIDENCE"

        reason = (
            f"Local multilingual NLI scores; max entailment={top_support:.3f}, "
            f"max contradiction={top_contradiction:.3f}, threshold={threshold:.2f}."
        )
        if exhausted:
            reason += " Pair limit reached; remaining evidence was not evaluated."
        results.append({
            "claim_id": claim_id,
            "status": status,
            "supported_source_ids": supported,
            "contradicting_source_ids": contradicted,
            "reason": reason,
            "evaluation_kind": "local_nli_assessment",
        })

    return json.dumps({"results": results}, ensure_ascii=False, separators=(",", ":"))


def judge_payload(payload: dict[str, Any]) -> str:
    """Serialize bounded runs and release runtime references even after failure.

    Releasing references allows ONNX memory reclamation; RSS reclamation is
    allocator-dependent and must be measured on the target machine.
    """
    with evaluation_session():
        return _judge_payload(payload)


@contextmanager
def evaluation_session():
    """Explicit bounded evaluation session; default judge still disposes per run."""
    with workload():
        try:
            yield _judge_payload
        finally:
            _MODEL_CACHE.clear()
