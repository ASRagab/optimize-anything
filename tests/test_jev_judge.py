"""Tests for the Jev evaluator. Transport is faked with httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from optimize_anything import jev_judge
from optimize_anything.jev_judge import jev_judge_evaluator

DIMS = [{"name": "clarity", "weight": 0.75}, {"name": "brevity", "weight": 0.25}]


def _answer(score: float, confidence: float = 0.9) -> dict[str, Any]:
    return {"type": "score", "score": score, "confidence": confidence}


def _ok(answers: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 2}},
    )


def _evaluator(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    kwargs.setdefault("quality_dimensions", DIMS)
    return jev_judge_evaluator("be clear", api_key="k", client=client, **kwargs)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(jev_judge.time, "sleep", lambda _s: None)


def test_weighted_sum_normalizes_by_top_level_and_uses_weights():
    # clarity 3/3 = 1.0 (w .75), brevity 1/3 (w .25) -> .75 + .0833
    ev = _evaluator(lambda r: _ok({"d0": _answer(3.0), "d1": _answer(1.0)}))
    score, info = ev("artifact text")
    assert score == pytest.approx(0.75 + 0.25 / 3)
    assert info["clarity"] == 1.0
    assert info["brevity"] == pytest.approx(1 / 3)
    assert info["jev_model"] == "jev-1.13.0"
    assert info["usage"] == {"input_tokens": 10, "output_tokens": 2}
    assert "clarity: 1.00" in info["reasoning"]


def test_hard_constraint_below_half_forces_zero():
    ev = _evaluator(
        lambda r: _ok({"d0": _answer(3.0), "d1": _answer(3.0), "c0": {"type": "noul", "noul": 0.49}}),
        hard_constraints=["no jargon"],
    )
    score, info = ev("x")
    assert score == 0.0
    assert info["hard_constraint_violation"] is True
    assert info["hard_constraints_satisfied"] is False


def test_hard_constraint_at_half_passes():
    ev = _evaluator(
        lambda r: _ok({"d0": _answer(3.0), "d1": _answer(3.0), "c0": {"type": "noul", "noul": 0.5}}),
        hard_constraints=["no jargon"],
    )
    score, info = ev("x")
    assert score == 1.0
    assert info["hard_constraints_satisfied"] is True


def test_request_shape_keeps_artifact_in_state_and_questions_narrow():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return _ok({"d0": _answer(2.0), "d1": _answer(2.0), "c0": {"type": "noul", "noul": 0.9}})

    ev = _evaluator(handler, hard_constraints=["no jargon"], model="jev-1.14.0")
    ev("the artifact", {"input": "ex"})
    body = seen["body"]
    assert seen["auth"] == "Bearer k"
    assert body["model"] == "jev-1.14.0"
    assert body["state"] == {"objective": "be clear", "artifact": "the artifact", "example": {"input": "ex"}}
    assert set(body["questions"]) == {"d0", "d1", "c0"}
    assert body["questions"]["d0"]["type"] == "score"
    assert len(body["questions"]["d0"]["criteria"]) == 4
    assert body["questions"]["c0"]["type"] == "noul"
    assert "no jargon" in body["questions"]["c0"]["instructions"]


def test_no_dimensions_uses_single_default_dimension():
    ev = jev_judge_evaluator(
        "obj",
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: _ok({"d0": _answer(3.0)}))),
    )
    score, info = ev("x")
    assert score == 1.0
    assert "overall quality" in info


def test_retries_429_then_succeeds_and_honors_retry_after(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(jev_judge.time, "sleep", waits.append)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"})
        return _ok({"d0": _answer(3.0), "d1": _answer(3.0)})

    score, _ = _evaluator(handler)("x")
    assert score == 1.0
    assert calls["n"] == 2
    assert waits == [2.0]


def test_persistent_5xx_gives_zero_after_bounded_attempts():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="down")

    score, info = _evaluator(handler)("x")
    assert score == 0.0
    assert calls["n"] == 3
    assert "HTTP 503" in info["error"]
    assert info["clarity"] == 0.0


def test_client_error_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(422, text="state too large")

    score, info = _evaluator(handler)("x")
    assert (score, calls["n"]) == (0.0, 1)
    assert "HTTP 422" in info["error"] and "state too large" in info["error"]


@pytest.mark.parametrize(
    "handler, message",
    [
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timed out"),
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("nope")), "request failed"),
        (lambda r: httpx.Response(200, text="not json"), "not valid JSON"),
        (lambda r: httpx.Response(200, json=[1]), "not a JSON object"),
        (lambda r: httpx.Response(200, json={"model": "m"}), "no 'answers'"),
        (lambda r: _ok({"d0": _answer(2.0)}), "d1"),
        (lambda r: _ok({"d0": {"type": "score", "score": "high", "confidence": 1}, "d1": _answer(1.0)}), "d0"),
    ],
)
def test_failures_return_zero_with_error_and_never_raise(handler, message):
    score, info = _evaluator(handler)("x")
    assert score == 0.0
    assert message in info["error"]


def test_out_of_range_score_is_clamped():
    score, info = _evaluator(lambda r: _ok({"d0": _answer(9.0), "d1": _answer(-1.0)}))("x")
    assert info["clarity"] == 1.0 and info["brevity"] == 0.0
    assert score == pytest.approx(0.75)


def test_missing_key_fails_fast_at_factory(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        jev_judge_evaluator("obj")


def test_blank_objective_rejected():
    with pytest.raises(ValueError, match="objective"):
        jev_judge_evaluator("  ", api_key="k")
