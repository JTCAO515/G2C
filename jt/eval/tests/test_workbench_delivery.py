import asyncio

from jt.common import SignalSink
from jt.engine.decision import MOCK_MODEL_VERSION, MockDecisionModel
from jt.engine.recognition import RecognitionEngine
from jt.engine.redaction import REDACTION_VERSION
from jt.engine.rules import RULES_VERSION
from jt.eval.dataset import generate_eval_cases
from jt.workbench.queue import MemoryQueue


def test_engine_delivers_synthetic_signals_to_workbench_via_shared_sink():
    cases = {case.case_id: case for case in generate_eval_cases()}
    queue = MemoryQueue()
    sink: SignalSink = queue
    engine = RecognitionEngine(sink, model=(MOCK_MODEL_VERSION, MockDecisionModel()))
    assert queue.snapshot() == ()

    async def deliver():
        urgent = await engine.recognize(cases["zh-lost"].events)
        document = await engine.recognize(cases["en-document"].events)
        replay = await engine.recognize(cases["zh-lost"].events)
        return urgent, document, replay

    urgent, document, replay = asyncio.run(deliver())

    first, second = queue.snapshot()
    assert first.signal == urgent.signal == replay.signal
    assert second.signal == document.signal
    assert (first.status, second.status) == ("pending", "pending")
    assert (first.case_id, second.case_id) == (None, None)
    assert (first.signal.severity, second.signal.severity) == ("P0", "P1")
    assert first.signal.redacted_fragments == ("我叫<NAME_1>和自己的家人走散了。",)
    assert first.signal.rule_hits == ("p0_safety",)
    assert first.signal.rules_version == RULES_VERSION
    assert first.signal.redaction_version == REDACTION_VERSION
    assert second.signal.model_outputs == (document.observation,)
    assert second.signal.model_outputs[0].model_version == MOCK_MODEL_VERSION
