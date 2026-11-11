"""AG-UI events, written by hand so every field is visible.

AG-UI (Agent-User Interaction protocol) is a TRANSPORT for agent <-> frontend:
a run is a stream of typed JSON events over SSE. It does not say what a UI
looks like; it says how text, tool calls and shared state reach the page.

    RUN_STARTED                          {threadId, runId}
    TEXT_MESSAGE_START/CONTENT/END       {messageId, role, delta}
    TOOL_CALL_START/ARGS/END             {toolCallId, toolCallName, delta}
    TOOL_CALL_RESULT                     {messageId, toolCallId, content}
    STATE_SNAPSHOT                       {snapshot}          the whole shared state
    STATE_DELTA                          {delta: [RFC 6902 ops]}
    CUSTOM                               {name, value}
    RUN_FINISHED / RUN_ERROR             {threadId, runId} / {message}

Field names are camelCase on the wire, exactly as the official @ag-ui/core
types; the official Python package (ag-ui-protocol) produces the same JSON.
"""

import json
from uuid import uuid4


def ev(kind, **fields):
    return {"type": kind, **fields}


def run_started(thread_id, run_id):
    return ev("RUN_STARTED", threadId=thread_id, runId=run_id)


def run_finished(thread_id, run_id):
    return ev("RUN_FINISHED", threadId=thread_id, runId=run_id)


def run_error(message):
    return ev("RUN_ERROR", message=message)


def text_message(text, chunk=24):
    """One assistant message as START, several CONTENT deltas, END."""
    mid = f"msg_{uuid4().hex[:8]}"
    yield ev("TEXT_MESSAGE_START", messageId=mid, role="assistant")
    for i in range(0, len(text), chunk):
        yield ev("TEXT_MESSAGE_CONTENT", messageId=mid, delta=text[i:i + chunk])
    yield ev("TEXT_MESSAGE_END", messageId=mid)


def tool_call(name, arguments, chunk=160, parent=None):
    """A tool call whose JSON arguments stream in pieces, as a model emits them."""
    cid = f"call_{uuid4().hex[:8]}"
    yield ev("TOOL_CALL_START", toolCallId=cid, toolCallName=name, parentMessageId=parent)
    raw = json.dumps(arguments)
    for i in range(0, len(raw), chunk):
        yield ev("TOOL_CALL_ARGS", toolCallId=cid, delta=raw[i:i + chunk])
    yield ev("TOOL_CALL_END", toolCallId=cid)
    return cid


def tool_result(call_id, content):
    return ev("TOOL_CALL_RESULT", messageId=f"msg_{uuid4().hex[:8]}", toolCallId=call_id, content=content, role="tool")


def state_snapshot(state):
    return ev("STATE_SNAPSHOT", snapshot=state)


def state_delta(ops):
    return ev("STATE_DELTA", delta=ops)


def run_input(prompt, state=None, messages=None, tools=None):
    """RunAgentInput: what the page POSTs to start a run."""
    return {"threadId": "thread_demo", "runId": f"run_{uuid4().hex[:8]}", "state": state or {},
            "messages": messages or [{"id": "u1", "role": "user", "content": prompt}],
            "tools": tools or [], "context": [], "forwardedProps": {}}
