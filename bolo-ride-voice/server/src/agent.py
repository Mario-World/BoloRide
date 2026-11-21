"""
Agent

High-level API for managing Agora Conversational AI Agents.
"""
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from agora_agent import Area, AsyncAgora
from agora_agent.agentkit import Agent as AgoraAgent
from agora_agent.agentkit.vendors import DeepgramSTT, MiniMaxTTS, OpenAI

from booking_tools import (
    BusinessApiClient,
    BookingToolRegistry,
    ToolRequestError,
    agora_tool_definitions,
)

logger = logging.getLogger("uvicorn.error")

BOLO_RIDE_PROMPT = """You are Bolo Ride's English-language ride-booking assistant.

Speak naturally and clearly in English. Collect pickup, destination, vehicle category, and passenger count progressively. Passenger name and payment preference are optional. Use validate_booking_details when the passenger gives or corrects trip information; preserve details already collected and ask only for missing or ambiguous information.

Use estimate_fare only when the trip details validate. Read back the pickup, destination, vehicle, passenger count, and backend fare, then ask whether the passenger explicitly confirms. Call create_booking only after a clear affirmative answer to that fare read-back; never treat silence, a question, or an earlier general request as confirmation. The booking tool requires explicit_confirmation="yes". After booking, report only the returned booking reference and status.

Do not invent locations, fares, bookings, drivers, or payment results. Offer cancellation through cancel_booking. Create a mock payment order only after the passenger asks to proceed; an order is not a successful payment. A successful simulated result remains pending until verify_payment returns status VERIFIED. Never ask for a UPI PIN, OTP, or banking credentials. Keep replies concise and ask the passenger to clarify unclear speech.
"""

VOICE_ONLY_PROMPT = """You are Bolo Ride's English-language voice assistant.

Speak naturally and clearly in English. Ride booking services are not configured in this session. Do not invent availability, prices, driver details, booking status, or payment outcomes, and do not claim a ride is booked or paid. Never request a UPI PIN or OTP. Keep replies concise and ask the rider to repeat or clarify when speech is unclear.
"""

DEFAULT_GREETING = "Hello, you're speaking with Bolo Ride. How can I help you today?"


class Agent:
    """
    High-level wrapper for Agora Conversational AI Agent operations.
    
    Uses AgentSession for full lifecycle management (start/stop),
    which handles Token007 authentication automatically.
    """
    
    def __init__(self):
        self.app_id = os.getenv("AGORA_APP_ID")
        self.app_certificate = os.getenv("AGORA_APP_CERTIFICATE")
        self.greeting = DEFAULT_GREETING

        if not self.app_id or not self.app_certificate:
            raise ValueError("AGORA_APP_ID and AGORA_APP_CERTIFICATE are required")

        business_api_url = os.getenv("BUSINESS_API_URL", "").strip()
        business_api_key = os.getenv("BUSINESS_API_KEY", "").strip()
        public_url = os.getenv("AGENT_PUBLIC_URL", "").strip().rstrip("/")
        self.tool_registry: BookingToolRegistry | None = None
        self.tool_public_url: str | None = None
        if business_api_url and business_api_key and public_url:
            parsed_url = urlparse(public_url)
            if parsed_url.scheme not in {"https", "http"} or not parsed_url.netloc:
                raise ValueError("AGENT_PUBLIC_URL must be an absolute HTTP(S) URL")
            self.tool_registry = BookingToolRegistry(
                BusinessApiClient(
                    base_url=business_api_url,
                    api_key=business_api_key,
                )
            )
            self.tool_public_url = public_url
        else:
            logger.warning(
                "booking_tools_disabled missing_server_configuration=%s",
                [
                    name
                    for name, value in (
                        ("BUSINESS_API_URL", business_api_url),
                        ("BUSINESS_API_KEY", business_api_key),
                        ("AGENT_PUBLIC_URL", public_url),
                    )
                    if not value
                ],
            )

        self.client = AsyncAgora(
            area=Area.US,
            app_id=self.app_id,
            app_certificate=self.app_certificate,
        )

        # Track active sessions by agent_id
        self._sessions: Dict[str, Any] = {}
        self._tool_tokens_by_agent: Dict[str, str] = {}

    async def start(
        self,
        channel_name: str,
        agent_uid: int,
        user_uid: int,
        output_audio_codec: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start agent with the same default vendor chain as the Next.js quickstart."""
        if not channel_name or not str(channel_name).strip():
            raise ValueError("channel_name is required and cannot be empty")
        if agent_uid <= 0:
            raise ValueError("agent_uid is required and cannot be empty")
        if user_uid <= 0:
            raise ValueError("user_uid is required and cannot be empty")

        # Default managed path: DeepgramSTT + OpenAI + MiniMaxTTS.
        tool_token = self.tool_registry.create_session() if self.tool_registry else None
        llm_options: dict[str, Any] = {
            "model": "gpt-4o-mini",
            "greeting_message": self.greeting,
            "failure_message": "Please wait a moment.",
            "max_history": 15,
            "max_tokens": 1024,
            "temperature": 0.7,
            "top_p": 0.95,
        }
        if tool_token and self.tool_public_url:
            llm_options["tools"] = agora_tool_definitions(self.tool_public_url)
            llm_options["template_variables"] = {"bolo_tool_token": tool_token}

        llm = OpenAI(**llm_options)
        stt = DeepgramSTT(model="nova-3", language="en")
        tts = MiniMaxTTS(model="speech_2_6_turbo", voice_id="English_captivating_female1")

        # Optional BYOK example: replace the STT block above and set DEEPGRAM_API_KEY.
        # stt = DeepgramSTT(api_key=os.getenv("DEEPGRAM_API_KEY"), model="nova-3", language="en")

        # Optional BYOK example: replace the LLM block above and set OPENAI_API_KEY.
        # llm = OpenAI(
        #     api_key=os.getenv("OPENAI_API_KEY"),
        #     model="gpt-4o-mini",
        #     greeting_message="Hello! I am your AI assistant. How can I help you?",
        #     failure_message="I'm sorry, I'm having trouble processing your request.",
        #     max_history=15,
        #     max_tokens=1024,
        #     temperature=0.7,
        #     top_p=0.95,
        # )

        # Optional BYOK example: replace the TTS block above and set ELEVENLABS_API_KEY.
        # from agora_agent.agentkit.vendors import ElevenLabsTTS
        # tts = ElevenLabsTTS(
        #     key=os.getenv("ELEVENLABS_API_KEY"),
        #     model_id="eleven_flash_v2_5",
        #     voice_id=os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB"),
        # )

        parameters = {
            "audio_scenario": "chorus",  # web client → ultra-low-latency chorus profile
            "data_channel": "rtm",
            "enable_error_message": True,
            "enable_metrics": True,
        }
        if isinstance(output_audio_codec, str) and output_audio_codec.strip():
            parameters["output_audio_codec"] = output_audio_codec.strip()

        agora_agent = AgoraAgent(
            client=self.client,
            instructions=BOLO_RIDE_PROMPT if tool_token else VOICE_ONLY_PROMPT,
            greeting=self.greeting,
            failure_message="Please wait a moment.",
            max_history=50,
            turn_detection={
                "config": {
                    "speech_threshold": 0.5,
                    "start_of_speech": {
                        "mode": "vad",
                        "vad_config": {
                            "interrupt_duration_ms": 160,
                            "prefix_padding_ms": 300,
                        },
                    },
                    "end_of_speech": {
                        "mode": "vad",
                        "vad_config": {
                            "silence_duration_ms": 480,
                        },
                    },
                },
            },
            advanced_features={"enable_rtm": True, "enable_tools": tool_token is not None},
            parameters=parameters,
        )
        
        agora_agent = (
            agora_agent
            .with_stt(stt)
            .with_llm(llm)
            .with_tts(tts)
        )

        session = agora_agent.create_async_session(
            channel=channel_name,
            agent_uid=str(agent_uid),
            remote_uids=[str(user_uid)],
            enable_string_uid=False,
            idle_timeout=30,
            expires_in=3600,
        )

        logger.info(
            "Starting Agora agent channel=%s agent_uid=%s user_uid=%s",
            channel_name,
            agent_uid,
            user_uid,
        )

        try:
            agent_id = await session.start()
        except Exception:
            if self.tool_registry:
                self.tool_registry.revoke_session(tool_token)
            logger.exception(
                "Failed to start Agora agent channel=%s agent_uid=%s user_uid=%s",
                channel_name,
                agent_uid,
                user_uid,
            )
            raise

        # Save session for later stop
        self._sessions[agent_id] = session
        if tool_token:
            self._tool_tokens_by_agent[agent_id] = tool_token

        logger.info(
            "Started Agora agent agent_id=%s channel=%s agent_uid=%s user_uid=%s",
            agent_id,
            channel_name,
            agent_uid,
            user_uid,
        )
        
        return {
            "agent_id": agent_id,
            "channel_name": channel_name,
            "status": "started",
        }

    async def invoke_tool(
        self,
        authorization: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.tool_registry is None:
            raise ToolRequestError(
                503,
                "booking_tools_disabled",
                "Booking tools are not configured on this server.",
            )
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token.strip():
            raise ToolRequestError(401, "invalid_tool_session", "A valid voice-session token is required.")
        return await self.tool_registry.invoke(token.strip(), tool_name, payload)

    async def stop(self, agent_id: str) -> None:
        """Stop a running agent. Falls back to the stateless client path."""
        if not agent_id or not str(agent_id).strip():
            raise ValueError("agent_id is required and cannot be empty")

        session = self._sessions.pop(agent_id, None)
        tool_token = self._tool_tokens_by_agent.pop(agent_id, None)
        try:
            if session:
                try:
                    await session.stop()
                    logger.info("Stopped Agora agent from active session agent_id=%s", agent_id)
                    return
                except Exception:
                    # Fall back to the stateless SDK path if the in-memory session is stale.
                    logger.warning(
                        "Failed to stop Agora agent from active session; falling back to client.stop_agent agent_id=%s",
                        agent_id,
                        exc_info=True,
                    )

            logger.info("Stopping Agora agent through client.stop_agent agent_id=%s", agent_id)
            await self.client.stop_agent(agent_id)
        finally:
            if self.tool_registry:
                self.tool_registry.revoke_session(tool_token)
