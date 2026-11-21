"""Agent env validation + managed-OpenAI wiring (SDK session monkeypatched)."""
import asyncio
import sys

import pytest


def _fresh_agent_module():
    sys.modules.pop("agent", None)
    import agent

    return agent


@pytest.mark.parametrize("missing", ["AGORA_APP_ID", "AGORA_APP_CERTIFICATE"])
def test_agent_requires_env(fake_env, monkeypatch, missing):
    monkeypatch.delenv(missing, raising=False)
    agent = _fresh_agent_module()
    with pytest.raises(ValueError):
        agent.Agent()


def test_agent_constructs_with_full_env(fake_env):
    agent = _fresh_agent_module()
    instance = agent.Agent()
    assert instance.app_id == "0123456789abcdef0123456789abcdef"
    assert instance.client is not None


def test_start_wires_managed_openai_and_returns_shape(fake_env, monkeypatch):
    for key in ("BUSINESS_API_URL", "BUSINESS_API_KEY", "AGENT_PUBLIC_URL"):
        monkeypatch.delenv(key, raising=False)
    agent = _fresh_agent_module()
    captured = {}
    original_agent_builder = agent.AgoraAgent

    def capture_vendor(factory_name, factory):
        def wrapped(**kwargs):
            captured[factory_name] = kwargs
            return factory(**kwargs)

        return wrapped

    monkeypatch.setattr(
        agent,
        "DeepgramSTT",
        capture_vendor("stt", agent.DeepgramSTT),
    )
    monkeypatch.setattr(
        agent,
        "MiniMaxTTS",
        capture_vendor("tts", agent.MiniMaxTTS),
    )

    def capture_agent_builder(**kwargs):
        captured["agent_config"] = kwargs
        return original_agent_builder(**kwargs)

    monkeypatch.setattr(agent, "AgoraAgent", capture_agent_builder)

    class FakeSession:
        async def start(self):
            return "test-agent-id"

        async def stop(self):
            captured["stopped"] = True

    def fake_create_async_session(self, **kwargs):
        captured["llm"] = self.llm
        captured["channel"] = kwargs.get("channel")
        captured["remote_uids"] = kwargs.get("remote_uids")
        return FakeSession()

    AgoraAgent = original_agent_builder

    monkeypatch.setattr(AgoraAgent, "create_async_session", fake_create_async_session)

    instance = agent.Agent()
    result = asyncio.run(instance.start(channel_name="ch", agent_uid=111, user_uid=222))

    assert result == {
        "agent_id": "test-agent-id",
        "channel_name": "ch",
        "status": "started",
    }
    # The LLM stage is the managed OpenAI vendor (gpt-4o-mini), NOT CustomLLM.
    assert captured["llm"]["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["llm"]["params"]["model"] == "gpt-4o-mini"
    assert captured["llm"]["style"] == "openai"
    assert "vendor" not in captured["llm"]  # managed OpenAI has no custom vendor key
    assert captured["channel"] == "ch"
    assert captured["remote_uids"] == ["222"]
    assert captured["stt"] == {"model": "nova-3", "language": "en"}
    assert captured["tts"] == {
        "model": "speech_2_6_turbo",
        "voice_id": "English_captivating_female1",
    }
    assert "Bolo Ride's English-language voice assistant" in captured["agent_config"]["instructions"]
    assert captured["agent_config"]["advanced_features"]["enable_rtm"] is True
    assert captured["agent_config"]["advanced_features"]["enable_tools"] is False
    assert (
        captured["agent_config"]["turn_detection"]["config"]["start_of_speech"]["vad_config"][
            "interrupt_duration_ms"
        ]
        == 160
    )


def test_start_enables_session_scoped_business_tools_when_configured(fake_env, monkeypatch):
    monkeypatch.setenv("BUSINESS_API_URL", "http://business-api.local")
    monkeypatch.setenv("BUSINESS_API_KEY", "business-secret-for-test")
    monkeypatch.setenv("AGENT_PUBLIC_URL", "https://voice.example.com")
    agent = _fresh_agent_module()
    captured = {}
    original_agent_builder = agent.AgoraAgent

    def capture_agent_builder(**kwargs):
        captured["agent_config"] = kwargs
        return original_agent_builder(**kwargs)

    monkeypatch.setattr(agent, "AgoraAgent", capture_agent_builder)

    class FakeSession:
        async def start(self):
            return "tool-enabled-agent"

        async def stop(self):
            captured["stopped"] = True

    def fake_create_session(self, **kwargs):
        captured["llm"] = self.llm
        return FakeSession()

    monkeypatch.setattr(original_agent_builder, "create_async_session", fake_create_session)

    instance = agent.Agent()
    result = asyncio.run(instance.start(channel_name="ch", agent_uid=111, user_uid=222))

    assert result["agent_id"] == "tool-enabled-agent"
    assert captured["agent_config"]["advanced_features"]["enable_tools"] is True
    assert "explicitly confirms" in captured["agent_config"]["instructions"]
    tool_names = {tool["function"]["name"] for tool in captured["llm"]["tools"]}
    assert {
        "validate_booking_details",
        "estimate_fare",
        "create_booking",
        "get_booking_status",
        "cancel_booking",
        "create_payment_order",
        "get_payment_status",
        "verify_payment",
    }.issubset(tool_names)
    assert "simulate_payment_result" not in tool_names
    assert "business-secret-for-test" not in repr(captured["llm"])
    assert captured["llm"]["tools"][0]["server"]["headers"] == {
        "Authorization": "Bearer {{template_variables.bolo_tool_token}}"
    }

    tool_token = captured["llm"]["template_variables"]["bolo_tool_token"]
    asyncio.run(instance.stop("tool-enabled-agent"))
    assert captured["stopped"] is True
    with pytest.raises(agent.ToolRequestError) as error:
        asyncio.run(instance.tool_registry.invoke(tool_token, "estimate_fare", {}))
    assert error.value.status_code == 401


def test_start_validates_arguments(fake_env, monkeypatch):
    agent = _fresh_agent_module()
    from agora_agent.agentkit import Agent as AgoraAgent

    monkeypatch.setattr(AgoraAgent, "create_async_session", lambda self, **k: None)
    instance = agent.Agent()
    with pytest.raises(ValueError):
        asyncio.run(instance.start(channel_name="", agent_uid=1, user_uid=2))
    with pytest.raises(ValueError):
        asyncio.run(instance.start(channel_name="c", agent_uid=0, user_uid=2))


def test_stop_uses_active_session_then_falls_back(fake_env, monkeypatch):
    agent = _fresh_agent_module()

    class FakeSession:
        def __init__(self):
            self.stopped = False

        async def start(self):
            return "agent-xyz"

        async def stop(self):
            self.stopped = True

    session = FakeSession()
    from agora_agent.agentkit import Agent as AgoraAgent

    monkeypatch.setattr(AgoraAgent, "create_async_session", lambda self, **k: session)
    instance = agent.Agent()

    fallback_calls = []

    async def fake_stop_agent(agent_id):
        fallback_calls.append(agent_id)

    monkeypatch.setattr(instance.client, "stop_agent", fake_stop_agent)

    asyncio.run(instance.start(channel_name="ch", agent_uid=111, user_uid=222))
    asyncio.run(instance.stop("agent-xyz"))
    assert session.stopped is True
    assert fallback_calls == []

    asyncio.run(instance.stop("unknown-id"))
    assert fallback_calls == ["unknown-id"]
