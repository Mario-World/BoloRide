"""FastAPI route tests via TestClient + FakeAgent (no Agora cloud)."""


def get_session_config(client):
    response = client.get("/get_config")
    assert response.status_code == 200
    return response.json()["data"]


def test_get_config_returns_secure_session_envelope(client):
    response = client.get("/get_config")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "success"
    data = body["data"]
    assert data["app_id"] == "0123456789abcdef0123456789abcdef"
    assert isinstance(data["token"], str) and len(data["token"]) > 0
    assert isinstance(data["session_ticket"], str) and len(data["session_ticket"]) > 0
    assert data["uid"].isdigit() and 1000 <= int(data["uid"]) <= 9_999_999
    assert data["channel_name"].startswith("bolo-ride-")
    assert 10_000_000 <= int(data["agent_uid"]) <= 99_999_999
    assert "fedcba9876543210fedcba9876543210" not in response.text


def test_get_config_requires_ticket_to_select_channel_or_uid(client):
    response = client.get("/get_config", params={"uid": 4321, "channel": "chosen-channel"})
    assert response.status_code == 400


def test_get_config_renews_only_the_signed_session(client):
    data = get_session_config(client)
    started = client.post(
        "/startAgent",
        json={
            "channelName": data["channel_name"],
            "rtcUid": int(data["agent_uid"]),
            "userUid": int(data["uid"]),
            "sessionTicket": data["session_ticket"],
        },
    ).json()["data"]
    response = client.get(
        "/get_config",
        params={
            "uid": data["uid"],
            "channel": data["channel_name"],
            "session_ticket": started["session_ticket"],
        },
    )
    assert response.status_code == 200
    renewed = response.json()["data"]
    assert renewed["channel_name"] == data["channel_name"]
    assert renewed["uid"] == data["uid"]
    assert renewed["agent_uid"] == data["agent_uid"]
    assert renewed["session_ticket"] == started["session_ticket"]


def test_get_config_rejects_tampered_or_mismatched_ticket(client):
    data = get_session_config(client)
    tampered = data["session_ticket"][:-1] + ("A" if data["session_ticket"][-1] != "A" else "B")
    params = {
        "uid": data["uid"],
        "channel": data["channel_name"],
        "session_ticket": tampered,
    }
    assert client.get("/get_config", params=params).status_code == 401

    params["session_ticket"] = data["session_ticket"]
    params["uid"] = str(int(data["uid"]) + 1)
    assert client.get("/get_config", params=params).status_code == 403


def test_get_config_rejects_expired_ticket(client, server_module):
    data = get_session_config(client)
    claims = server_module._read_session_ticket(data["session_ticket"])
    claims["expires_at"] = 1
    expired_ticket = server_module._create_session_ticket(claims)
    response = client.get(
        "/get_config",
        params={
            "uid": data["uid"],
            "channel": data["channel_name"],
            "session_ticket": expired_ticket,
        },
    )
    assert response.status_code == 401


def test_start_agent_requires_and_binds_session_ticket(client):
    data = get_session_config(client)
    payload = {
        "channelName": data["channel_name"],
        "rtcUid": int(data["agent_uid"]),
        "userUid": int(data["uid"]),
        "sessionTicket": data["session_ticket"],
    }
    response = client.post("/startAgent", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["agent_id"] == f"fake-agent-{data['agent_uid']}"
    assert body["data"]["session_ticket"] != data["session_ticket"]
    assert client.fake_agent.started == [
        (data["channel_name"], int(data["agent_uid"]), int(data["uid"]), None)
    ]


def test_start_agent_rejects_ticket_replay_and_returns_same_start(client):
    data = get_session_config(client)
    payload = {
        "channelName": data["channel_name"],
        "rtcUid": int(data["agent_uid"]),
        "userUid": int(data["uid"]),
        "sessionTicket": data["session_ticket"],
    }
    first = client.post("/startAgent", json=payload)
    second = client.post("/startAgent", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    assert len(client.fake_agent.started) == 1


def test_start_agent_rejects_wrong_session(client):
    data = get_session_config(client)
    response = client.post(
        "/startAgent",
        json={
            "channelName": "other-channel",
            "rtcUid": int(data["agent_uid"]),
            "userUid": int(data["uid"]),
            "sessionTicket": data["session_ticket"],
        },
    )
    assert response.status_code == 403


def test_start_agent_forwards_output_audio_codec(client):
    data = get_session_config(client)
    client.post(
        "/startAgent",
        json={
            "channelName": data["channel_name"],
            "rtcUid": int(data["agent_uid"]),
            "userUid": int(data["uid"]),
            "sessionTicket": data["session_ticket"],
            "parameters": {"output_audio_codec": "opus"},
        },
    )
    assert client.fake_agent.started[-1] == (
        data["channel_name"],
        int(data["agent_uid"]),
        int(data["uid"]),
        "opus",
    )


def test_stop_agent_requires_ticket_bound_to_agent(client):
    data = get_session_config(client)
    start = client.post(
        "/startAgent",
        json={
            "channelName": data["channel_name"],
            "rtcUid": int(data["agent_uid"]),
            "userUid": int(data["uid"]),
            "sessionTicket": data["session_ticket"],
        },
    ).json()["data"]
    payload = {
        "agentId": start["agent_id"],
        "channelName": data["channel_name"],
        "userUid": int(data["uid"]),
        "sessionTicket": start["session_ticket"],
    }
    response = client.post("/stopAgent", json=payload)
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert client.fake_agent.stopped == [start["agent_id"]]

    payload["agentId"] = "another-agent"
    assert client.post("/stopAgent", json=payload).status_code == 403


def test_value_error_maps_to_400(client, server_module):
    class BadAgent:
        async def start(self, **kwargs):
            raise ValueError("bad input")

        async def stop(self, *args):
            pass

    data = get_session_config(client)
    server_module.agent = BadAgent()
    response = client.post(
        "/startAgent",
        json={
            "channelName": data["channel_name"],
            "rtcUid": int(data["agent_uid"]),
            "userUid": int(data["uid"]),
            "sessionTicket": data["session_ticket"],
        },
    )
    assert response.status_code == 400
    assert "bad input" in response.json()["detail"]


def test_runtime_error_maps_to_sanitized_500(client, server_module):
    class BoomAgent:
        async def start(self, **kwargs):
            raise RuntimeError("internal provider details")

        async def stop(self, *args):
            pass

    data = get_session_config(client)
    server_module.agent = BoomAgent()
    response = client.post(
        "/startAgent",
        json={
            "channelName": data["channel_name"],
            "rtcUid": int(data["agent_uid"]),
            "userUid": int(data["uid"]),
            "sessionTicket": data["session_ticket"],
        },
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Agora agent operation failed"
    assert "internal provider details" not in response.text


def test_misconfigured_agent_returns_500(client, server_module):
    server_module.agent = None
    assert client.get("/get_config").status_code == 500
    assert (
        client.post(
            "/startAgent",
            json={
                "channelName": "bolo-ride-channel",
                "rtcUid": 10_000_000,
                "userUid": 1000,
                "sessionTicket": "a" * 16,
            },
        ).status_code
        == 500
    )
    assert (
        client.post(
            "/stopAgent",
            json={
                "agentId": "agent-id",
                "channelName": "bolo-ride-channel",
                "userUid": 1000,
                "sessionTicket": "a" * 16,
            },
        ).status_code
        == 500
    )
