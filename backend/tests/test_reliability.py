import pytest


def test_pass_metrics_distinguish_one_success_from_consistency():
    from paylane.reliability import pass_metrics

    m = pass_metrics(7, 6)
    assert m["pass_at_7"] == 1
    assert m["pass_pow_7"] == 0
    assert m["pass_at_1"] == pytest.approx(6 / 7)
    assert m["pass_pow_3"] == pytest.approx(4 / 7)


def test_all_successes_do_not_imply_certain_reliability():
    from paylane.reliability import pass_metrics

    m = pass_metrics(7, 7)
    assert m["pass_pow_7"] == 1
    assert 0.6 < m["wilson_95"][0] < 0.7
    assert m["wilson_95"][1] == pytest.approx(1)


def test_missing_trials_fail_release_gate():
    from paylane.reliability import aggregate

    case = {"id": "C01", "title": "Refund", "suite": "required"}
    trials = [
        {
            "id": "C01",
            "trial": i,
            "passed": True,
            "checks": [],
            "metrics": [],
            "transcript": [],
        }
        for i in range(1, 7)
    ]
    r = aggregate([case], trials, 7)
    assert not r["release_gate_passed"]
    assert r["completed"] == 6 and r["expected"] == 7
    assert r["cases"][0]["metrics"]["pass_pow_7"] is None


def test_failed_trial_stays_in_denominator_and_attack_outcome_is_separate():
    from paylane.reliability import aggregate

    case = {"id": "A01", "title": "Attack", "suite": "adversarial"}
    trials = [
        {
            "id": "A01",
            "trial": i,
            "passed": i != 3,
            "checks": [],
            "metrics": [],
            "transcript": [],
            "security": {
                "attack_succeeded": False,
                "unsafe_attempts": 1 if i == 3 else 0,
            },
        }
        for i in range(1, 8)
    ]
    r = aggregate([case], trials, 7)
    assert r["passed"] == 6 and r["completed"] == 7 and not r["release_gate_passed"]
    assert r["security"]["attack_success_rate"] == 0
    assert r["security"]["unsafe_attempt_trials"] == 1


def test_cohort_fingerprint_change_cannot_resume(tmp_path):
    from paylane.reliability import initialize_cohort

    initialize_cohort(tmp_path, {"fingerprint": "one"}, 7, ["C01"], 3)
    with pytest.raises(ValueError, match="cohort_configuration_changed"):
        initialize_cohort(tmp_path, {"fingerprint": "two"}, 7, ["C01"], 3)


def test_interrupted_started_trial_is_preserved_as_failure(tmp_path):
    from paylane.reliability import TrialJournal

    j = TrialJournal(tmp_path, "frozen")
    j.start("C01", 1)
    resumed = TrialJournal(tmp_path, "frozen")
    results = resumed.recover_interrupted()
    assert len(results) == 1 and not results[0]["passed"]
    assert results[0]["evaluation_mode"] == "interrupted"
    with pytest.raises(ValueError, match="trial_already_started"):
        resumed.start("C01", 1)


def test_prompt_change_invalidates_full_cohort_configuration():
    from paylane.reliability import assert_frozen

    with pytest.raises(ValueError, match="cohort_configuration_changed"):
        assert_frozen(
            {"source": "same", "prompts": {"system": "one"}},
            {"source": "same", "prompts": {"system": "two"}},
        )


def test_trial_with_wrong_fingerprint_cannot_be_loaded(tmp_path):
    from paylane.reliability import TrialJournal

    j = TrialJournal(tmp_path, "one")
    j.start("C01", 1)
    with pytest.raises(ValueError, match="trial_fingerprint_mismatch"):
        TrialJournal(tmp_path, "two").recover_interrupted()


def test_resume_does_not_replace_interruption_or_returned_failures(
    tmp_path, monkeypatch
):
    import paylane.reliability as r

    backend = tmp_path / "backend"
    (backend / "scenarios").mkdir(parents=True)
    for f in ["adversarial.json", "benign-controls.json"]:
        (backend / "scenarios" / f).write_text("[]")
    c = {"id": "C01", "title": "Test", "why": "Test", "expect": {}}
    monkeypatch.setattr(r, "BACKEND", backend)
    monkeypatch.setattr(r, "load_cases", lambda: [c])
    monkeypatch.setattr(r, "provenance", lambda: {"source_fingerprint": "frozen"})
    monkeypatch.setattr(r, "frozen_configuration", lambda *_: {"source": "frozen"})
    calls = []

    def execute(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise KeyboardInterrupt()
        return c | {
            "passed": False,
            "checks": [],
            "metrics": [],
            "transcript": [],
            "evaluation_mode": "full",
        }

    monkeypatch.setattr(r, "run_case", execute)
    first = r.run_cohort(tmp_path / "cohort", workers=1, progress=lambda *_: None)
    assert (
        len(calls) == 7
        and first["summary"]["completed"] == 7
        and first["summary"]["passed"] == 0
    )
    monkeypatch.setattr(
        r,
        "run_case",
        lambda *a, **kw: pytest.fail("Completed/started trials must never be replaced"),
    )
    resumed = r.run_cohort(tmp_path / "cohort", workers=1, progress=lambda *_: None)
    assert (
        resumed["summary"]["passed"] == 0
        and not resumed["summary"]["release_gate_passed"]
    )


def test_recovered_contract_violations_remain_visible_in_aggregate():
    from paylane.reliability import aggregate

    case = {"id": "C01", "title": "Refund"}
    trial = {
        "id": "C01",
        "trial": 1,
        "passed": True,
        "checks": [],
        "metrics": [],
        "transcript": [
            {
                "result": {
                    "events": [{"tool": "agent_model", "phase": "contract_violation"}],
                    "usage": [{"_contract_repairs": 1, "_usage": {}}],
                }
            }
        ],
    }
    r = aggregate([case], [trial], 7)
    assert r["operational"]["tool_contract_violations"] == 1
    assert r["operational"]["classifier_contract_repairs"] == 1
