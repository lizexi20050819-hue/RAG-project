from file_history_store import ChatHistoryStore


def test_trim_keeps_last_rounds():
    msgs = []
    for i in range(10):
        msgs.append({"role": "user", "content": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})

    trimmed = ChatHistoryStore.trim(msgs, max_rounds=3)
    assert len(trimmed) == 6
    assert trimmed[0]["content"] == "q7"
    assert trimmed[-1]["content"] == "a9"


def test_trim_zero_rounds_returns_empty():
    msgs = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    assert ChatHistoryStore.trim(msgs, max_rounds=0) == []

