import json

import pytest
from fastapi.testclient import TestClient

from reviewpulse.app import assisted_review, interpret
from reviewpulse.app.api import create_app
from reviewpulse.app.store import Store
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.schema import Inputs, Program
from reviewpulse.rules.clauses import Clause


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create("Timed test").id
    text = "The building height must be at least 4 m."
    context = ContextBundle(document="test", text=text, target="q", clauses=[
        Clause(id="q", heading="", page=0, text=text, start=0, end=len(text))])
    program = Program(id="I-q", title="Height", document="test", requirement={"node":"ge",
        "left":{"node":"fact","entity":"building","name":"height"},
        "right":{"node":"literal","value":4,"unit":"m"}},
        sources=[{"clause":"q","start":0,"end":len(text),"quote":text}])
    inputs = Inputs(bindings={"height":{"kind":"number","unit":"m","description":"Building height"}},
        facts={"building":{"height":{"value":3,"trusted":True,"source":"fixture"}}})
    interpret._save(store,pid,{"q":{"arm":"assisted","status":"DRAFTED","queue":"in_scope_draft","program":program.model_dump(mode="json")}})
    monkeypatch.setattr(interpret,"_context",lambda *args:context)
    monkeypatch.setattr(interpret,"_plan",lambda *args:(None,inputs,None))
    clock=[100.0]
    monkeypatch.setattr(assisted_review.time,"time",lambda:clock[0])
    with TestClient(create_app(tmp_path,llm=lambda:None)) as client:
        yield client,store,pid,clock,context


def test_timer_pause_failed_attempt_diff_and_approval_without_hosted_model(env):
    client,store,pid,clock,_=env
    base=f"/api/projects/{pid}/assisted"
    session=client.post(base+"/session",json={"clause":"q","reviewer":"Tester","actor_type":"test"}).json()
    assert session["before"]["subject"]
    clock[0]=110
    assert client.post(base+"/session/pause",json={"session_id":session["id"],"paused":True}).status_code==200
    clock[0]=140
    assert client.post(base+"/session/save",json={"session_id":session["id"],"text":"{}"}).status_code==409
    client.post(base+"/session/pause",json={"session_id":session["id"],"paused":False})
    clock[0]=145
    bad=client.post(base+"/session/save",json={"session_id":session["id"],"text":"{}","input_events":1}).json()
    assert not bad["saved"] and bad["session"]["elapsed_seconds"]==15
    assert client.post(base+"/approve",json={"clause":"q","action":"approve","reviewer":"Tester","acknowledge":True}).status_code==409
    clock[0]=146
    good=client.post(base+"/session/save",json={"session_id":session["id"],"text":json.dumps(session["before"]),"input_events":2})
    assert good.status_code==200,good.text
    assert good.json()["saved"] and good.json()["session"]["elapsed_seconds"]==16
    assert good.json()["entry"]["preview"]["outcome"]=="VIOLATED"
    assert "approved_program" not in good.json()["entry"]
    assert client.post(base+"/approve",json={"clause":"q","action":"approve","reviewer":"Tester","acknowledge":False}).status_code==409
    approved=client.post(base+"/approve",json={"clause":"q","action":"approve","reviewer":"Tester","acknowledge":True})
    assert approved.status_code==200,approved.text
    assert approved.json()["approved_program"]["status"]=="approved"
    report=client.get(base+"/effort").json()
    assert report["observed_sessions"]==0 and report["excluded_sessions"]==1
    assert len(assisted_review._load(store,pid)[session["id"]]["attempts"])==2


def test_stale_source_cannot_overwrite_draft(env,monkeypatch):
    client,_,pid,_,context=env
    base=f"/api/projects/{pid}/assisted"
    session=client.post(base+"/session",json={"clause":"q","reviewer":"Tester","actor_type":"test"}).json()
    monkeypatch.setattr(interpret,"_context",lambda *args:context.model_copy(update={"document":"changed"}))
    response=client.post(base+"/session/save",json={"session_id":session["id"],"text":json.dumps(session["before"])})
    assert response.status_code==409 and "changed" in response.text


def test_diff_preserves_added_scope_and_changed_units():
    changes=assisted_review.diff({"unit":"m","scope":[]},{"unit":"mm","scope":[{"zone":"Q"}]})
    assert {c["path"] for c in changes}=={"/unit","/scope"}
