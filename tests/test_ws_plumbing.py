"""WebSocket frame classification in receive_stream_message()."""

import pytest

from speech_engine.core.stt.base import (
    MSG_AUDIO,
    MSG_DISCONNECT,
    MSG_FLUSH,
    MSG_NOOP,
    MSG_STOP,
    receive_stream_message,
)


class FakeWS:
    def __init__(self, messages):
        self._messages = list(messages)

    async def receive(self):
        return self._messages.pop(0)


@pytest.mark.asyncio
async def test_message_classification():
    ws = FakeWS(
        [
            {"type": "websocket.receive", "bytes": b"\x01\x02"},
            {"type": "websocket.receive", "text": '{"event": "flush"}'},
            {"type": "websocket.receive", "text": "stop"},
            {"type": "websocket.receive", "text": "hello"},
            {"type": "websocket.disconnect"},
        ]
    )
    assert await receive_stream_message(ws) == (MSG_AUDIO, b"\x01\x02")
    assert (await receive_stream_message(ws))[0] == MSG_FLUSH
    assert (await receive_stream_message(ws))[0] == MSG_STOP
    assert (await receive_stream_message(ws))[0] == MSG_NOOP
    assert (await receive_stream_message(ws))[0] == MSG_DISCONNECT


@pytest.mark.asyncio
async def test_disconnect_on_runtime_error():
    class BrokenWS:
        async def receive(self):
            raise RuntimeError("connection closed")

    assert await receive_stream_message(BrokenWS()) == (MSG_DISCONNECT, b"")
