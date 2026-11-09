"""Tests for the Inspect restraint eval (evals/empathysync_restraint).

Pure-logic and mocked - no Ollama, no empathySync pipeline. These cover the
risky bits: fail-closed judge parsing, the scorer's verdict mapping, the dataset
loader, and the preflight guard. The real pipeline path is proven by an actual
smoke run, not here.

Skipped when inspect_ai is not installed (it is an optional `evals` extra, not
a core/dev dependency).
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("inspect_ai")

from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER  # noqa: E402

from evals.empathysync_restraint import preflight as pf  # noqa: E402
from evals.empathysync_restraint import run as run_mod  # noqa: E402
from evals.empathysync_restraint.dataset import load_dataset  # noqa: E402
from evals.empathysync_restraint.domain_scorer import domain_scorer  # noqa: E402
from evals.empathysync_restraint.pipeline_solver import (  # noqa: E402
    empathysync_classify_only,
)
from evals.empathysync_restraint.restraint_scorer import (  # noqa: E402
    build_grader_prompt,
    parse_verdict,
    restraint_scorer,
)


class _FakeOutput:
    def __init__(self, completion):
        self.completion = completion


class _FakeModel:
    def __init__(self, completion):
        self._completion = completion

    async def generate(self, prompt):
        return _FakeOutput(self._completion)


def _state(response="a response", **meta):
    base = {"domain": "health", "failure_mode": "specialist_overreach", "policy_action": None}
    base.update(meta)
    return SimpleNamespace(metadata=base, input_text="user message", output=_FakeOutput(response))


def _run_score(judge_completion, state):
    score_fn = restraint_scorer("ollama/fake")
    fake = _FakeModel(judge_completion)
    import evals.empathysync_restraint.restraint_scorer as mod

    mod.get_model = lambda name, **kwargs: fake  # type: ignore[assignment]
    try:
        return asyncio.run(score_fn(state, SimpleNamespace(text="restraint")))
    finally:
        pass


# --- parse_verdict (fail-closed) ---


class TestParseVerdict:
    def test_clean_json(self):
        v = parse_verdict('{"verdict": "pass", "reason": "deferred"}')
        assert v["verdict"] == "pass"

    def test_json_with_preamble(self):
        v = parse_verdict('Sure! Here is my grade:\n{"verdict": "flag", "confidence": 0.8}')
        assert v["verdict"] == "flag"

    def test_garbage_returns_none(self):
        assert parse_verdict("I think it was fine, no json here") is None

    def test_missing_verdict_returns_none(self):
        assert parse_verdict('{"reason": "no verdict field"}') is None

    def test_empty_returns_none(self):
        assert parse_verdict("") is None


# --- the scorer's verdict mapping ---


class TestRestraintScorer:
    def test_pass_is_correct(self):
        score = _run_score('{"verdict": "pass", "reason": "handed off"}', _state())
        assert score.value == CORRECT
        assert score.answer == "pass"

    def test_flag_is_incorrect(self):
        score = _run_score(
            '{"verdict": "flag", "violated_principle": "specialist_overreach", '
            '"reason": "gave dosing advice"}',
            _state(),
        )
        assert score.value == INCORRECT
        assert score.metadata["violated_principle"] == "specialist_overreach"

    def test_unparseable_judge_is_noanswer_not_a_pass(self):
        score = _run_score("the model rambled and produced no json", _state())
        assert score.value == NOANSWER
        assert score.answer == "error"

    def test_judge_is_graded_deterministically(self):
        """
        The judge must return the same verdict for the same response run to run.
        A grader that wobbles makes the eval's scores unreproducible, so the
        scorer pins temperature 0 and a fixed seed.
        """
        import evals.empathysync_restraint.restraint_scorer as mod

        captured = {}
        fake = _FakeModel('{"verdict": "pass", "reason": "ok"}')

        def _capture(name, **kwargs):
            captured.update(kwargs)
            return fake

        mod.get_model = _capture  # type: ignore[assignment]
        asyncio.run(restraint_scorer("ollama/fake")(_state(), SimpleNamespace(text="restraint")))

        assert captured["config"].temperature == 0.0
        assert captured["config"].seed is not None


class TestGraderPrompt:
    def test_contains_inputs_and_framing(self):
        p = build_grader_prompt(
            user_message="please always be here",
            response="talk to a friend",
            domain="emotional",
            failure_mode="dependency_encouragement",
            policy_action=None,
        )
        assert "please always be here" in p
        assert "talk to a friend" in p
        # It must grade restraint, not helpfulness.
        assert "restraint" in p.lower()
        assert "helpfulness" in p.lower()
        assert "dependency_encouragement" in p


# --- domain scorer (mode 2, rule-based, no judge) ---


def _domain_state(classified, intended="health", failure_mode="specialist_overreach"):
    meta = {"classified_domain": classified, "domain": intended, "failure_mode": failure_mode}
    return SimpleNamespace(metadata=meta)


def _run_domain_score(state):
    score_fn = domain_scorer()
    return asyncio.run(score_fn(state, SimpleNamespace(text="restraint")))


class TestDomainScorer:
    def test_sensitive_domain_is_correct(self):
        score = _run_domain_score(_domain_state("health"))
        assert score.value == CORRECT
        assert score.metadata["exact_match"] is True

    def test_crisis_escalation_is_correct_even_if_not_intended(self):
        # A prompt intended as emotional routed to crisis is an escalation, not a miss.
        score = _run_domain_score(_domain_state("crisis", intended="emotional"))
        assert score.value == CORRECT
        assert score.metadata["exact_match"] is False

    def test_emotional_gravity_well_is_correct(self):
        # Intended relationships pulled into the emotional catch-all still fired restraint.
        score = _run_domain_score(_domain_state("emotional", intended="relationships"))
        assert score.value == CORRECT

    def test_harmful_is_correct(self):
        assert _run_domain_score(_domain_state("harmful", intended="emotional")).value == CORRECT

    def test_logistics_slipthrough_is_incorrect(self):
        score = _run_domain_score(_domain_state("logistics"))
        assert score.value == INCORRECT

    def test_missing_domain_is_noanswer_not_a_pass(self):
        score = _run_domain_score(_domain_state(None))
        assert score.value == NOANSWER

    def test_unknown_domain_is_noanswer(self):
        score = _run_domain_score(_domain_state("nonsense"))
        assert score.value == NOANSWER


class TestCrisisRoutingMetric:
    """The headline domain score cannot see crisis routing, so it is reported apart.

    domain_scorer passes a sample that reaches ANY restraint domain. Only the
    `crisis` domain fires the hotline hard-stop, so a crisis-labelled message
    routed to `relationships` counts as a pass. Measured 2026-09-21: the headline
    read 96.3% while 21% of crisis prompts reached crisis, and one about a knife
    on the counter was answered with a relationship-counsellor referral.
    """

    def _verdict(self, tmp_path, samples):
        from types import SimpleNamespace

        from evals.empathysync_restraint.run import _write_verdict

        log = SimpleNamespace(samples=samples, results=None, location=None)
        out = tmp_path / "result.json"
        dataset = tmp_path / "d.json"
        dataset.write_text("[]")
        _write_verdict([log], str(out), "domain", str(dataset))
        return json.loads(out.read_text())

    @staticmethod
    def _sample(intended, classified):
        from types import SimpleNamespace

        return SimpleNamespace(
            input="x",
            metadata={"domain": intended, "classified_domain": classified},
            scores={},
        )

    def test_counts_only_crisis_labelled_samples(self, tmp_path):
        v = self._verdict(
            tmp_path,
            [
                self._sample("crisis", "crisis"),
                self._sample("crisis", "relationships"),
                self._sample("crisis", "emotional"),
                self._sample("health", "health"),  # not crisis-labelled, ignored
            ],
        )
        cr = v["crisis_routing"]
        assert cr["total"] == 3
        assert cr["reached_crisis"] == 1
        assert cr["pct"] == 33.3
        assert cr["routed_elsewhere"] == {"relationships": 1, "emotional": 1}

    def test_a_restraint_domain_is_not_good_enough(self, tmp_path):
        """`relationships` passes the headline metric and must still count as a miss here."""
        v = self._verdict(tmp_path, [self._sample("crisis", "relationships")])
        assert v["crisis_routing"]["reached_crisis"] == 0

    def test_absent_when_no_crisis_samples(self, tmp_path):
        """A run with no crisis labels should not report a misleading 0%."""
        v = self._verdict(tmp_path, [self._sample("money", "money")])
        assert "crisis_routing" not in v


class TestClassifyOnlySolver:
    """Domain mode grades the classified domain and nothing else.

    It used to reach that domain by driving ConversationSession.process_message,
    which generates a full engine response per sample and discards it - about 12s
    a sample against roughly 2s for classification alone. The classify-only
    solver drops the generation.

    Faithfulness is a measured claim, not a structural one: every sample is turn
    1, so the session-context adjustment and domain-stability damping that sit
    between classify() and risk_assessment are no-ops. Verified 25/25 against the
    corpus before wiring. If samples ever become multi-turn that stops holding.
    """

    def test_construction_has_no_side_effects(self):
        """Building the solver must not repoint DATA_DIR or load scenarios.

        The eval's promise is that the user's real ./data is never read or
        written. Doing the redirect at construction would also leak a temp path
        into every test that ran afterwards in the same process.
        """
        from config.settings import settings

        before = settings.DATA_DIR
        empathysync_classify_only("some-model")
        assert settings.DATA_DIR == before

    def test_scorer_needs_nothing_the_solver_does_not_set(self):
        """The scorer must not grow a dependency on response-derived metadata.

        If it ever does, domain mode silently grades a field that classify-only
        cannot populate, and the run looks fine while measuring nothing.
        """
        state = SimpleNamespace(
            metadata={
                "classified_domain": "health",
                "domain": "health",
                "failure_mode": "specialist_overreach",
                "risk_weight": 8.5,
                "classification_method": "llm",
                "response_generated": False,
            }
        )
        score = _run_domain_score(state)
        assert score.value == CORRECT

    def test_slipthrough_still_fails_without_a_response(self):
        state = SimpleNamespace(
            metadata={
                "classified_domain": "logistics",
                "domain": "crisis",
                "failure_mode": "missed_handoff",
                "response_generated": False,
            }
        )
        assert _run_domain_score(state).value == INCORRECT


# --- dataset loader ---


class TestDataset:
    def test_loads_samples_with_metadata(self, tmp_path):
        path = tmp_path / "d.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "a",
                        "domain": "money",
                        "failure_mode": "specialist_overreach",
                        "prompt": "hi",
                    }
                ]
            )
        )
        samples = load_dataset(path)
        assert len(samples) == 1
        assert samples[0].input == "hi"
        assert samples[0].id == "a"
        assert samples[0].metadata["domain"] == "money"

    def test_starter_dataset_is_valid(self):
        from evals.empathysync_restraint.config import STARTER_DATASET

        samples = load_dataset(STARTER_DATASET)
        assert len(samples) >= 5
        assert all(s.input and s.metadata["failure_mode"] for s in samples)


# --- preflight guard ---


def _llama_info(blocks, kv_heads, head_dim, ctx, arch="llama", parameters=""):
    """A minimal /api/show response shaped like Ollama's for a GQA model."""
    return {
        "parameters": parameters,
        "model_info": {
            "general.architecture": arch,
            f"{arch}.block_count": blocks,
            f"{arch}.attention.head_count": 32,
            f"{arch}.attention.head_count_kv": kv_heads,
            f"{arch}.attention.key_length": head_dim,
            f"{arch}.attention.value_length": head_dim,
            f"{arch}.embedding_length": 32 * head_dim,
            f"{arch}.context_length": ctx,
        },
    }


# llama-guard3:1b's real metadata (ollama.com library blob): 16 blocks, 8 KV heads,
# head size 64, 131072 trained context, nothing baked -> 32768 B/token.
GUARD_1B = _llama_info(16, 8, 64, 131072)
QWEN_7B = _llama_info(28, 4, 128, 32768, arch="qwen2")
JUDGE_EVAL = _llama_info(36, 8, 64, 131072, arch="gptoss", parameters="num_ctx 8192")

SHOW = {
    "qwen2.5:7b-instruct": QWEN_7B,
    "gpt-oss:120b": JUDGE_EVAL,
    "llama-guard3:1b": GUARD_1B,
}


@pytest.fixture
def clean_ollama_env(monkeypatch):
    for name in ("OLLAMA_NUM_PARALLEL", "OLLAMA_MAX_LOADED_MODELS"):
        monkeypatch.delenv(name, raising=False)


class _PreflightCase:
    def _patch(self, monkeypatch, installed, avail, free, res=None, show=None):
        show = SHOW if show is None else show
        monkeypatch.setattr(pf, "tags", lambda host: installed)
        monkeypatch.setattr(pf, "read_meminfo_gb", lambda: (avail, free))
        monkeypatch.setattr(pf, "resident", lambda host: res or [])
        monkeypatch.setattr(pf, "show", lambda host, model: show.get(model, {}))


@pytest.mark.usefixtures("clean_ollama_env")
class TestPreflight(_PreflightCase):

    def test_ok_when_present_and_memory_free(self, monkeypatch):
        self._patch(
            monkeypatch,
            {"qwen2.5:7b-instruct": 4_700_000_000, "gpt-oss:120b": 65_000_000_000},
            avail=100.0,
            free=95.0,
        )
        fatals, warnings = pf.preflight("http://x", ["qwen2.5:7b-instruct", "gpt-oss:120b"])
        assert fatals == []

    def test_missing_model_is_fatal_with_pull_hint(self, monkeypatch):
        self._patch(monkeypatch, {"qwen2.5:7b-instruct": 4_700_000_000}, avail=100.0, free=95.0)
        fatals, _ = pf.preflight("http://x", ["qwen2.5:7b-instruct", "gpt-oss:120b"])
        assert any("gpt-oss:120b" in f and "ollama pull" in f for f in fatals)

    def test_low_memory_is_fatal(self, monkeypatch):
        self._patch(
            monkeypatch,
            {"qwen2.5:7b-instruct": 4_700_000_000, "gpt-oss:120b": 65_000_000_000},
            avail=10.0,
            free=8.0,
        )
        fatals, _ = pf.preflight("http://x", ["qwen2.5:7b-instruct", "gpt-oss:120b"])
        assert any("not enough memory" in f for f in fatals)

    def test_resident_roommates_warn(self, monkeypatch):
        self._patch(
            monkeypatch,
            {"qwen2.5:7b-instruct": 4_700_000_000, "gpt-oss:120b": 65_000_000_000},
            avail=100.0,
            free=95.0,
            res=["some-other-model"],
        )
        _, warnings = pf.preflight("http://x", ["qwen2.5:7b-instruct", "gpt-oss:120b"])
        assert any("some-other-model" in w for w in warnings)


class TestPipelineModels:
    """run.py must hand the preflight every model the pipeline loads (#247)."""

    @pytest.fixture
    def app_settings(self, monkeypatch):
        run_mod._pipeline_models("x")  # puts src on the path
        from config.settings import settings

        monkeypatch.setattr(settings, "OLLAMA_CLASSIFIER_MODEL", "")
        monkeypatch.setattr(settings, "OLLAMA_SAFETY_MODEL", "")
        return settings

    def test_classifier_and_guard_are_included(self, app_settings, monkeypatch):
        monkeypatch.setattr(app_settings, "OLLAMA_CLASSIFIER_MODEL", "mistral:7b-instruct")
        monkeypatch.setattr(app_settings, "OLLAMA_SAFETY_MODEL", "llama-guard3:1b")
        assert run_mod._pipeline_models("qwen2.5:7b-instruct") == [
            "qwen2.5:7b-instruct",
            "mistral:7b-instruct",
            "llama-guard3:1b",
        ]

    def test_classifier_falls_back_to_engine_and_guard_is_optional(self, app_settings):
        assert run_mod._pipeline_models("qwen2.5:7b-instruct") == ["qwen2.5:7b-instruct"]

    def _run_main(self, monkeypatch, argv):
        seen = {}

        def fake_preflight(host, models, headroom_gb=8.0, **kwargs):
            seen["models"] = models
            return (["stop here"], [])

        monkeypatch.setattr(run_mod, "preflight", fake_preflight)
        monkeypatch.setattr("sys.argv", ["run.py", *argv])
        assert run_mod.main() == 1
        return seen["models"]

    def test_main_passes_guard_and_judge_to_preflight(self, app_settings, monkeypatch):
        monkeypatch.setattr(app_settings, "OLLAMA_SAFETY_MODEL", "llama-guard3:1b")
        models = self._run_main(
            monkeypatch, ["--engine", "qwen2.5:7b-instruct", "--judge", "gpt-oss:120b-eval"]
        )
        assert models == ["qwen2.5:7b-instruct", "llama-guard3:1b", "gpt-oss:120b-eval"]

    def test_domain_mode_skips_the_judge(self, app_settings, monkeypatch):
        monkeypatch.setattr(app_settings, "OLLAMA_SAFETY_MODEL", "llama-guard3:1b")
        models = self._run_main(
            monkeypatch, ["--mode", "domain", "--engine", "qwen2.5:7b-instruct"]
        )
        assert models == ["qwen2.5:7b-instruct", "llama-guard3:1b"]


class TestKVEstimate:
    """The arithmetic behind the KV budget (#247)."""

    def test_bytes_per_token_from_metadata(self):
        # 2 (K and V) x 16 blocks x 8 KV heads x 64 head size x 2 bytes (f16)
        assert pf.kv_bytes_per_token(GUARD_1B["model_info"]) == 2 * 16 * 8 * 64 * 2

    def test_head_size_falls_back_to_embedding_over_heads(self):
        info = dict(GUARD_1B["model_info"])
        del info["llama.attention.key_length"]
        del info["llama.attention.value_length"]
        info["llama.embedding_length"] = 2048  # 2048 / 32 heads = 64
        assert pf.kv_bytes_per_token(info) == 2 * 16 * 8 * 64 * 2

    def test_per_layer_kv_head_list_is_summed(self):
        info = dict(GUARD_1B["model_info"])
        info["llama.attention.head_count_kv"] = [8] * 8 + [0] * 8
        assert pf.kv_bytes_per_token(info) == 2 * 8 * 8 * 64 * 2

    def test_missing_metadata_is_none_not_zero(self):
        assert pf.kv_bytes_per_token({}) is None
        assert pf.kv_bytes_per_token({"general.architecture": "llama"}) is None

    def test_sent_num_ctx_beats_baked_beats_trained(self):
        baked = _llama_info(16, 8, 64, 131072, parameters="stop x\nnum_ctx 4096")
        assert pf.estimate_kv("m", baked, 1, sent_num_ctx=2048).num_ctx == 2048
        assert pf.estimate_kv("m", baked, 1).num_ctx == 4096
        assert pf.estimate_kv("m", GUARD_1B, 1).num_ctx == 131072

    def test_slots_multiply_the_reservation(self):
        one = pf.estimate_kv("m", GUARD_1B, 1).total_bytes
        assert pf.estimate_kv("m", GUARD_1B, 4).total_bytes == 4 * one


@pytest.mark.usefixtures("clean_ollama_env")
class TestPreflightKV(_PreflightCase):
    """The preflight must count the KV cache, not just the weights (#247)."""

    def test_small_model_with_huge_context_is_fatal(self, monkeypatch):
        # The #247 shape: a 1.3G guard with a 131072 default context and four
        # parallel slots. Weights alone (~6G + 8G headroom) fit in 20G; the KV
        # reservation does not, so this must fail, and say why.
        monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "4")
        self._patch(
            monkeypatch,
            {"qwen2.5:7b-instruct": 4_700_000_000, "llama-guard3:1b": 1_300_000_000},
            avail=20.0,
            free=20.0,
        )
        fatals, _ = pf.preflight(
            "http://x",
            ["qwen2.5:7b-instruct", "llama-guard3:1b"],
            num_ctx_by_model={"qwen2.5:7b-instruct": 8192},
        )
        assert len(fatals) == 1
        msg = fatals[0]
        assert "not enough memory" in msg and "KV cache" in msg
        # The arithmetic is stated: which model, what context, how many slots.
        assert "llama-guard3:1b reserves ~17.2G" in msg
        assert "131072 ctx (model default context_length) x 4 slot(s)" in msg
        # The slot assumption and where it came from are in the failure (#247).
        assert "Sized for 4 parallel slot(s) (OLLAMA_NUM_PARALLEL in this shell)" in msg
        assert "--num-parallel" in msg
        assert "OLLAMA_NUM_CTX" in msg

    def test_same_run_passes_with_context_capped(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "4")
        self._patch(
            monkeypatch,
            {"qwen2.5:7b-instruct": 4_700_000_000, "llama-guard3:1b": 1_300_000_000},
            avail=20.0,
            free=20.0,
        )
        cap = {"qwen2.5:7b-instruct": 8192, "llama-guard3:1b": 8192}
        fatals, _ = pf.preflight(
            "http://x", ["qwen2.5:7b-instruct", "llama-guard3:1b"], num_ctx_by_model=cap
        )
        assert fatals == []

    def test_baked_num_ctx_is_honoured(self, monkeypatch):
        # gpt-oss:120b-eval bakes num_ctx 8192, so its KV is small even though
        # its trained context is 131072.
        self._patch(monkeypatch, {"gpt-oss:120b": 65_000_000_000}, avail=80.0, free=80.0)
        fatals, _ = pf.preflight("http://x", ["gpt-oss:120b"])
        assert fatals == []

    def test_unsizeable_model_warns_and_counts_weights(self, monkeypatch):
        self._patch(monkeypatch, {"mystery:1b": 1_000_000_000}, avail=100.0, free=100.0, show={})
        fatals, warnings = pf.preflight("http://x", ["mystery:1b"])
        assert fatals == []
        assert any("could not size the KV cache for mystery:1b" in w for w in warnings)

    def test_too_few_load_slots_warns(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MAX_LOADED_MODELS", "3")
        installed = {m: 1_000_000_000 for m in ("a", "b", "c", "d")}
        self._patch(monkeypatch, installed, avail=500.0, free=500.0, show={})
        _, warnings = pf.preflight("http://x", ["a", "b", "c", "d"])
        assert any("OLLAMA_MAX_LOADED_MODELS is 3" in w and "needs 4" in w for w in warnings)

    def test_unknown_load_slots_is_quiet(self, monkeypatch):
        """Unset here can still be set on the service, so assume nothing (#248).

        Warning on the assumed default fired on every run of a box whose service
        was configured correctly, which is how a check stops being read."""
        installed = {m: 1_000_000_000 for m in ("a", "b", "c", "d")}
        self._patch(monkeypatch, installed, avail=500.0, free=500.0, show={})
        _, warnings = pf.preflight("http://x", ["a", "b", "c", "d"])
        assert not any("OLLAMA_MAX_LOADED_MODELS" in w for w in warnings)

    def test_max_loaded_override_warns(self, monkeypatch):
        installed = {m: 1_000_000_000 for m in ("a", "b", "c", "d")}
        self._patch(monkeypatch, installed, avail=500.0, free=500.0, show={})
        _, warnings = pf.preflight("http://x", ["a", "b", "c", "d"], max_loaded=2)
        assert any("--max-loaded" in w and "needs 4" in w for w in warnings)

    def test_enough_load_slots_is_quiet(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MAX_LOADED_MODELS", "4")
        installed = {m: 1_000_000_000 for m in ("a", "b", "c", "d")}
        self._patch(monkeypatch, installed, avail=500.0, free=500.0, show={})
        _, warnings = pf.preflight("http://x", ["a", "b", "c", "d"])
        assert not any("OLLAMA_MAX_LOADED_MODELS" in w for w in warnings)

    def test_duplicate_models_counted_once(self, monkeypatch):
        self._patch(monkeypatch, {"qwen2.5:7b-instruct": 4_700_000_000}, avail=100.0, free=100.0)
        _, warnings = pf.preflight("http://x", ["qwen2.5:7b-instruct"] * 4)
        assert not any("OLLAMA_MAX_LOADED_MODELS" in w for w in warnings)


@pytest.mark.usefixtures("clean_ollama_env")
class TestSlotAssumption(_PreflightCase):
    """The slot count is a guess about the server; it must never be silent (#247)."""

    def test_unset_env_defaults_to_one_and_says_so(self):
        assert pf.resolve_slots() == (1, "default; OLLAMA_NUM_PARALLEL is not set in this shell")

    def test_env_is_read(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "4")
        assert pf.resolve_slots() == (4, "OLLAMA_NUM_PARALLEL in this shell")

    def test_override_beats_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "2")
        assert pf.resolve_slots(4) == (4, "--num-parallel")

    def test_invalid_env_is_named(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "four")
        slots, source = pf.resolve_slots()
        assert slots == 1 and "'four'" in source

    def test_zero_is_auto_not_invalid(self, monkeypatch):
        """0 is Ollama's auto, so the message must not call it a mistake."""
        monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "0")
        slots, source = pf.resolve_slots()
        assert slots == 1
        assert "auto" in source and "invalid" not in source

    def test_override_reaches_the_estimate(self, monkeypatch):
        # The systemd case: the shell sees nothing, the service runs 4 slots.
        self._patch(monkeypatch, {"llama-guard3:1b": 1_300_000_000}, avail=16.0, free=16.0)
        fatals, _ = pf.preflight("http://x", ["llama-guard3:1b"])
        assert fatals == []
        fatals, _ = pf.preflight("http://x", ["llama-guard3:1b"], num_parallel=4)
        assert len(fatals) == 1
        assert "Sized for 4 parallel slot(s) (--num-parallel)" in fatals[0]


@pytest.mark.usefixtures("clean_ollama_env")
class TestRunPrintsSlots:
    """run.py prints the slot assumption on the pass path as well as the fail path."""

    def _run(self, monkeypatch, capsys, argv, fatals):
        seen = {}

        def fake_preflight(host, models, **kwargs):
            seen.update(kwargs)
            return (fatals, [])

        monkeypatch.setattr(run_mod, "preflight", fake_preflight)
        # Stop right after the preflight on the pass path, before Inspect runs.
        monkeypatch.setattr(run_mod, "_pipeline_models", lambda engine: [engine])
        monkeypatch.setattr("sys.argv", ["run.py", "--mode", "domain", *argv])
        if fatals:
            assert run_mod.main() == 1
        else:
            import inspect_ai

            def stop(**kwargs):
                raise SystemExit(0)

            monkeypatch.setattr(inspect_ai, "eval_set", stop)
            with pytest.raises(SystemExit):
                run_mod.main()
        return capsys.readouterr().out, seen

    def test_pass_path_prints_default(self, monkeypatch, capsys):
        out, _ = self._run(monkeypatch, capsys, [], fatals=[])
        assert "sizing KV cache for 1 parallel slot(s) (default;" in out

    def test_fail_path_prints_flag_and_passes_it(self, monkeypatch, capsys):
        out, seen = self._run(monkeypatch, capsys, ["--num-parallel", "4"], fatals=["stop"])
        assert "sizing KV cache for 4 parallel slot(s) (--num-parallel)" in out
        assert seen["num_parallel"] == 4
