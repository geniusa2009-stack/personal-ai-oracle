import pytest

import bounded_correction


def test_valid_first_attempt_does_not_call_repair():
    calls = []
    result = bounded_correction.run_bounded_correction(
        lambda: "valid response",
        lambda *_: calls.append("repair") or "repaired",
        lambda value: [] if value == "valid response" else ["bad_response"],
    )

    assert result.output == "valid response"
    assert result.corrected is False
    assert result.retry_count == 0
    assert result.stop_reason == "validated_first_attempt"
    assert calls == []


def test_validation_failure_gets_exactly_one_bounded_repair():
    generated = []
    repairs = []

    def generate():
        generated.append("initial")
        return "invalid"

    def repair(previous, issues, attempt):
        repairs.append((previous, issues, attempt))
        return "valid"

    result = bounded_correction.run_bounded_correction(
        generate,
        repair,
        lambda value: [] if value == "valid" else ["invalid_shape"],
    )

    assert result.output == "valid"
    assert result.corrected is True
    assert result.retry_count == 1
    assert result.stop_reason == "validated_after_retry"
    assert generated == ["initial"]
    assert repairs == [("invalid", ("invalid_shape",), 1)]


def test_repeated_output_stops_loop_without_a_third_call():
    calls = []

    def repair(previous, issues, attempt):
        calls.append((previous, issues, attempt))
        return previous

    result = bounded_correction.run_bounded_correction(
        lambda: "still invalid",
        repair,
        lambda _value: ["invalid_json"],
        max_retries=2,
    )

    assert result.output == "still invalid"
    assert result.stop_reason == "repeated_output"
    assert result.retry_count == 1
    assert len(result.attempts) == 2
    assert len(calls) == 1


def test_repeated_validation_signature_stops_even_when_text_changes():
    values = iter(["bad output one", "bad output two", "bad output three"])
    calls = []

    result = bounded_correction.run_bounded_correction(
        lambda: next(values),
        lambda *_: calls.append(True) or next(values),
        lambda _value: ["same_validation_problem"],
        max_retries=2,
    )

    assert result.stop_reason == "repeated_validation_issues"
    assert result.retry_count == 1
    assert len(result.attempts) == 2
    assert len(calls) == 1


def test_non_retryable_provider_error_does_not_duplicate_provider_failure():
    calls = []

    result = bounded_correction.run_bounded_correction(
        lambda: "(تعذّر التشغيل: provider unavailable)",
        lambda *_: calls.append(True) or "second attempt",
        lambda _value: ["provider_error"],
    )

    assert result.stop_reason == "non_retryable_issue"
    assert result.retry_count == 0
    assert result.final_issue_codes == ("provider_error",)
    assert calls == []


def test_retry_policy_hard_cap_and_callback_arguments_are_validated():
    with pytest.raises(bounded_correction.CorrectionError):
        bounded_correction.run_bounded_correction(
            lambda: "x", lambda *_: "x", lambda _x: [], max_retries=3
        )
    with pytest.raises(bounded_correction.CorrectionError):
        bounded_correction.run_bounded_correction(
            "not-callable", lambda *_: "x", lambda _x: []
        )
    with pytest.raises(bounded_correction.CorrectionError):
        bounded_correction.run_bounded_correction(
            lambda: "x", lambda *_: "x", lambda _x: [], max_output_chars=0
        )


def test_correction_report_contains_metadata_only_not_answer_content():
    result = bounded_correction.run_bounded_correction(
        lambda: "secret invalid output",
        lambda *_: "secret valid output",
        lambda text: [] if text == "secret valid output" else ["invalid_shape"],
    )
    serialized = str(result.to_dict())

    assert result.corrected is True
    assert "secret valid output" not in serialized
    assert "secret invalid output" not in serialized
    assert result.attempts[0].output_fingerprint



def test_generation_exception_is_counted_as_failed_attempt_without_retry():
    result = bounded_correction.run_bounded_correction(
        lambda: (_ for _ in ()).throw(RuntimeError("sensitive provider response")),
        lambda *_: "should not run",
        lambda _value: [],
    )

    assert result.stop_reason == "generation_error"
    assert result.retry_count == 0
    assert len(result.attempts) == 1
    assert result.attempts[0].passed is False
    assert result.final_issue_codes == ("runtimeerror",)
    assert "sensitive provider response" not in str(result.to_dict())


def test_repair_exception_is_counted_as_a_retry_attempt():
    result = bounded_correction.run_bounded_correction(
        lambda: "invalid",
        lambda *_: (_ for _ in ()).throw(TimeoutError("sensitive timeout detail")),
        lambda _value: ["invalid_shape"],
    )

    assert result.stop_reason == "repair_error"
    assert result.retry_count == 1
    assert len(result.attempts) == 2
    assert result.attempts[-1].passed is False
    assert result.final_issue_codes == ("timeouterror",)
    assert "sensitive timeout detail" not in str(result.to_dict())
