from collections import Counter

from jt.synthetic import DEFAULT_SEED, generate_dataset


def test_dataset_reproduces_content_order_and_ids_for_a_seed():
    dataset = generate_dataset()
    replay = generate_dataset(DEFAULT_SEED)
    assert dataset == replay
    assert dataset != generate_dataset(DEFAULT_SEED + 1)
    assert [record.model_dump_json() for record in (*dataset.events, *dataset.signals)] == [
        record.model_dump_json() for record in (*replay.events, *replay.signals)
    ]


def test_dataset_covers_each_level_and_uses_only_synthetic_references():
    dataset = generate_dataset(1706)
    events = {event.ref.event_id: event for event in dataset.events}

    assert len(events) == len(dataset.events)
    assert len({value.signal_id for value in dataset.signals}) == len(dataset.signals)
    assert set(Counter(value.signal_type for value in dataset.signals).values()) == {2}
    assert len({value.signal_type for value in dataset.signals}) == 8
    assert {value.severity for value in dataset.signals} == {"P0", "P1", "P2", "P3", "P4"}
    assert {event.ref.event_type for event in dataset.events} == {
        "intent_unresolved", "message_accepted", "order_status_changed", "tool_failed", "trip_time_triggered",
    }

    for value in dataset.signals:
        assert value.signal_id.startswith("sig-syn-")
        assert all(ref == events[ref.event_id].ref for ref in value.source_events)
        assert all(ref.event_id.startswith("evt-syn-") for ref in value.source_events)
        assert all(ref.conversation_id.startswith("conv-syn-") for ref in value.source_events)
        message = events[value.source_events[0].event_id]
        assert message.ref.event_type == "message_accepted"
        assert message.ref.message_id.startswith("msg-syn-")
        assert value.redacted_fragments == (message.synthetic_fragment,)
        assert value.detected_at > max(ref.occurred_at for ref in value.source_events)
        if value.severity == "P0":
            assert value.rule_hits and not value.model_outputs

    assert all(
        (event.synthetic_fragment is not None) == (event.ref.event_type == "message_accepted")
        for event in dataset.events
    )
