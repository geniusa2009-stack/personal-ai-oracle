"""Bounded, loop-aware correction for text-only model outputs.

This module accepts only text generators, text repair callbacks and validators.
It has no tool executor and cannot repeat local actions, browser actions, or
other side effects. The caller supplies explicit validation rules.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable, Sequence


DEFAULT_MAX_RETRIES = 1
MAX_CORRECTION_RETRIES = 2
MAX_OUTPUT_CHARS = 12000
MAX_ISSUES = 8
MAX_ISSUE_LENGTH = 80


class CorrectionError(ValueError):
    """Invalid correction policy or callback result."""


@dataclass(frozen=True)
class CorrectionAttempt:
    attempt_number: int
    output_fingerprint: str
    issue_codes: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class CorrectionResult:
    output: str
    attempts: tuple[CorrectionAttempt, ...]
    corrected: bool
    stop_reason: str
    final_issue_codes: tuple[str, ...]

    @property
    def retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)

    def to_dict(self) -> dict[str, object]:
        """Return metadata only; never include the generated text."""
        return {
            "status": (
                "corrected" if self.corrected
                else "valid_first_attempt" if self.attempts and self.attempts[0].passed
                else "not_corrected"
            ),
            "attempt_count": len(self.attempts),
            "retry_count": self.retry_count,
            "corrected": self.corrected,
            "stop_reason": self.stop_reason,
            "final_issue_codes": list(self.final_issue_codes),
            "attempts": [
                {
                    "attempt_number": item.attempt_number,
                    "output_fingerprint": item.output_fingerprint,
                    "issue_codes": list(item.issue_codes),
                    "passed": item.passed,
                }
                for item in self.attempts
            ],
        }


Generator = Callable[[], str]
Repair = Callable[[str, tuple[str, ...], int], str]
Validator = Callable[[str], Sequence[str]]


def _issue_codes(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple, set, frozenset)):
        raise CorrectionError("validator must return a sequence of issue codes")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise CorrectionError("validator issue codes must be strings")
        code = value.strip().lower()
        if not code or len(code) > MAX_ISSUE_LENGTH or not re.fullmatch(r"[a-z0-9_.-]+", code):
            raise CorrectionError("validator returned an invalid issue code")
        if code not in result:
            result.append(code)
        if len(result) >= MAX_ISSUES:
            break
    return tuple(result)


def _fingerprint(output: str) -> str:
    normalized = " ".join(output.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_bounded_correction(
    generate: Generator,
    repair: Repair,
    validate: Validator,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    non_retryable_issues: Sequence[str] = ("provider_error",),
    max_output_chars: int = MAX_OUTPUT_CHARS,
) -> CorrectionResult:
    """Generate once, then repair only validation failures within a hard retry cap.

    No retry occurs for a valid answer, a non-retryable issue, a repeated output
    fingerprint, a repeated validation signature, or an exhausted retry budget.
    """
    if not callable(generate) or not callable(repair) or not callable(validate):
        raise CorrectionError("generate, repair and validate must be callable")
    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or not 0 <= max_retries <= MAX_CORRECTION_RETRIES
    ):
        raise CorrectionError(f"max_retries must be between 0 and {MAX_CORRECTION_RETRIES}")
    if (
        isinstance(max_output_chars, bool)
        or not isinstance(max_output_chars, int)
        or not 1 <= max_output_chars <= MAX_OUTPUT_CHARS
    ):
        raise CorrectionError(f"max_output_chars must be between 1 and {MAX_OUTPUT_CHARS}")

    blocked = _issue_codes(tuple(non_retryable_issues))
    attempts: list[CorrectionAttempt] = []
    fingerprints: set[str] = set()
    validation_signatures: set[tuple[str, ...]] = set()
    current_output = ""
    previous_issues: tuple[str, ...] = ()
    corrected = False

    for attempt_number in range(max_retries + 1):
        try:
            raw_output = generate() if attempt_number == 0 else repair(
                current_output, previous_issues, attempt_number
            )
        except Exception as exc:
            stop_reason = "generation_error" if attempt_number == 0 else "repair_error"
            return CorrectionResult(
                output=current_output,
                attempts=tuple(attempts),
                corrected=False,
                stop_reason=stop_reason,
                final_issue_codes=(type(exc).__name__.lower(),),
            )

        if not isinstance(raw_output, str):
            issue_codes = ("non_text_output",)
            output = ""
        else:
            output = raw_output[:max_output_chars]
            issue_codes = ()
            if len(raw_output) > max_output_chars:
                issue_codes = ("output_too_long",)
            else:
                try:
                    issue_codes = _issue_codes(validate(output))
                except Exception as exc:
                    issue_codes = (f"validator_{type(exc).__name__.lower()}",)

        fingerprint = _fingerprint(output)
        if fingerprint in fingerprints:
            attempts.append(CorrectionAttempt(
                attempt_number=attempt_number + 1,
                output_fingerprint=fingerprint,
                issue_codes=issue_codes or previous_issues,
                passed=False,
            ))
            return CorrectionResult(
                output=current_output,
                attempts=tuple(attempts),
                corrected=False,
                stop_reason="repeated_output",
                final_issue_codes=previous_issues or issue_codes,
            )

        fingerprints.add(fingerprint)
        passed = not issue_codes
        attempts.append(CorrectionAttempt(
            attempt_number=attempt_number + 1,
            output_fingerprint=fingerprint,
            issue_codes=issue_codes,
            passed=passed,
        ))
        current_output = output

        if passed:
            corrected = attempt_number > 0
            return CorrectionResult(
                output=current_output,
                attempts=tuple(attempts),
                corrected=corrected,
                stop_reason="validated_after_retry" if corrected else "validated_first_attempt",
                final_issue_codes=(),
            )

        if set(issue_codes) & set(blocked):
            return CorrectionResult(
                output=current_output,
                attempts=tuple(attempts),
                corrected=False,
                stop_reason="non_retryable_issue",
                final_issue_codes=issue_codes,
            )

        if attempt_number >= max_retries:
            return CorrectionResult(
                output=current_output,
                attempts=tuple(attempts),
                corrected=False,
                stop_reason="retry_limit_reached",
                final_issue_codes=issue_codes,
            )

        if issue_codes in validation_signatures:
            return CorrectionResult(
                output=current_output,
                attempts=tuple(attempts),
                corrected=False,
                stop_reason="repeated_validation_issues",
                final_issue_codes=issue_codes,
            )
        validation_signatures.add(issue_codes)
        previous_issues = issue_codes

    return CorrectionResult(
        output=current_output,
        attempts=tuple(attempts),
        corrected=False,
        stop_reason="retry_limit_reached",
        final_issue_codes=previous_issues,
    )
