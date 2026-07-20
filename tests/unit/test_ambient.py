"""Heartbeat decision + quiet hours helpers."""

from tagopen.ambient.heartbeat import build_observation, decide_heartbeat


def test_heartbeat_dedupe_and_post():
    class T:
        id = "tsk_abc"
        status = type("S", (), {"value": "waiting_approval"})()
        objective = "Do a thing"

    from tagopen.ambient import heartbeat as hb

    hb._recent_nudge_hashes.clear()
    obs = build_observation([T()], ["stale thread"])
    d1 = decide_heartbeat(obs)
    assert d1["action"] == "post"
    hb._recent_nudge_hashes[d1["hash"]] = __import__("time").time()
    d2 = decide_heartbeat(obs)
    assert d2["action"] == "silent"
