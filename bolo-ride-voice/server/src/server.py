# -*- coding: utf-8 -*-
"""FastAPI routes for Agora tokens and Conversational AI sessions."""
import base64
import asyncio
import binascii
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_base_dir, ".env"))

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agora_agent.agentkit.token import generate_convo_ai_token
from agent import Agent

logger = logging.getLogger("uvicorn.error")

TOKEN_TTL_SECONDS = 3600
SESSION_TICKET_CONTEXT = b"bolo-ride-agora-session-ticket-v1"
USER_UID_MIN = 1000
USER_UID_MAX = 9_999_999
AGENT_UID_MIN = 10_000_000
AGENT_UID_MAX = 99_999_999


def _log_route_error(route: str, exc: Exception, **context: Any) -> None:
    safe_context = {key: value for key, value in context.items() if value is not None}
    logger.error(
        "request_failed route=%s context=%s error_type=%s",
        route,
        safe_context,
        type(exc).__name__,
    )


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Agora agent operation failed")


def _ticket_signing_key() -> bytes:
    certificate = os.getenv("AGORA_APP_CERTIFICATE")
    if not certificate:
        raise RuntimeError("Agora App Certificate is not configured")
    return hmac.new(
        certificate.encode("utf-8"),
        SESSION_TICKET_CONTEXT,
        hashlib.sha256,
    ).digest()


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _create_session_ticket(claims: Dict[str, Any]) -> str:
    payload = _urlsafe_encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _ticket_signing_key(),
        payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload}.{_urlsafe_encode(signature)}"


def _read_session_ticket(ticket: str, *, allow_expired: bool = False) -> Dict[str, Any]:
    try:
        payload, encoded_signature = ticket.split(".", 1)
        signature = _urlsafe_decode(encoded_signature)
        expected_signature = hmac.new(
            _ticket_signing_key(),
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("invalid signature")

        claims = json.loads(_urlsafe_decode(payload))
        if (
            not isinstance(claims, dict)
            or claims.get("version") != 1
            or not isinstance(claims.get("expires_at"), int)
            or not isinstance(claims.get("channel"), str)
            or not isinstance(claims.get("uid"), int)
            or not isinstance(claims.get("agent_uid"), int)
            or not isinstance(claims.get("ticket_id"), str)
        ):
            raise ValueError("invalid claims")
        if not allow_expired and claims["expires_at"] <= int(time.time()):
            raise ValueError("expired ticket")
        return claims
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired session ticket")


def _require_matching_ticket(
    ticket: str,
    *,
    channel: str,
    uid: int,
    require_agent_id: bool,
    allow_expired: bool = False,
) -> Dict[str, Any]:
    claims = _read_session_ticket(ticket, allow_expired=allow_expired)
    if claims["channel"] != channel or claims["uid"] != uid:
        raise HTTPException(status_code=403, detail="Session ticket does not match this session")
    has_agent_id = isinstance(claims.get("agent_id"), str) and bool(claims["agent_id"])
    if has_agent_id != require_agent_id:
        raise HTTPException(status_code=403, detail="Session ticket is not valid for this operation")
    return claims


try:
    agent = Agent()
except ValueError:
    logger.error("agora_agent_initialization_failed error_type=ValueError")
    agent = None


app = FastAPI(
    title="Bolo Ride Voice Agent",
    version="1.0.0",
    description="English voice conversation service using Agora Conversational AI",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "AGENT_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

router = APIRouter()
_start_locks: Dict[str, asyncio.Lock] = {}
_started_sessions: Dict[str, Dict[str, Any]] = {}


class StartAgentRequest(BaseModel):
    channelName: str = Field(min_length=1, max_length=64)
    rtcUid: int = Field(gt=AGENT_UID_MIN - 1, le=AGENT_UID_MAX)
    userUid: int = Field(ge=USER_UID_MIN, le=USER_UID_MAX)
    sessionTicket: str = Field(min_length=16, max_length=8192)
    parameters: Optional[Dict[str, Any]] = None


class StopAgentRequest(BaseModel):
    agentId: str = Field(min_length=1, max_length=128)
    channelName: str = Field(min_length=1, max_length=64)
    userUid: int = Field(ge=USER_UID_MIN, le=USER_UID_MAX)
    sessionTicket: str = Field(min_length=16, max_length=8192)


def _generate_channel_name() -> str:
    return f"bolo-ride-{secrets.token_urlsafe(24)}"


def _new_session_claims(channel_name: str, user_uid: int, agent_uid: int) -> Dict[str, Any]:
    return {
        "version": 1,
        "ticket_id": secrets.token_urlsafe(18),
        "channel": channel_name,
        "uid": user_uid,
        "agent_uid": agent_uid,
        "expires_at": int(time.time()) + TOKEN_TTL_SECONDS,
    }


def _prune_expired_started_sessions() -> None:
    now = int(time.time())
    expired_ids = [
        ticket_id
        for ticket_id, started in _started_sessions.items()
        if started["expires_at"] <= now
    ]
    for ticket_id in expired_ids:
        _started_sessions.pop(ticket_id, None)
        _start_locks.pop(ticket_id, None)


@router.get("/get_config")
async def get_config(
    channel: Optional[str] = Query(default=None, min_length=1, max_length=64),
    uid: Optional[int] = Query(default=None, ge=USER_UID_MIN, le=USER_UID_MAX),
    session_ticket: Optional[str] = Query(default=None, min_length=16, max_length=8192),
):
    """Create a session or issue a renewal token for its signed session ticket."""
    if agent is None:
        raise HTTPException(
            status_code=500,
            detail="Service not properly configured. Check server environment variables.",
        )

    if session_ticket is None:
        if channel is not None or uid is not None:
            raise HTTPException(
                status_code=400,
                detail="Channel and UID can only be supplied with a valid session ticket",
            )
        channel_name = _generate_channel_name()
        user_uid = secrets.randbelow(USER_UID_MAX - USER_UID_MIN + 1) + USER_UID_MIN
        agent_uid = secrets.randbelow(AGENT_UID_MAX - AGENT_UID_MIN + 1) + AGENT_UID_MIN
        claims = _new_session_claims(channel_name, user_uid, agent_uid)
        ticket = _create_session_ticket(claims)
    else:
        if channel is None or uid is None:
            raise HTTPException(
                status_code=400,
                detail="Channel and UID are required when renewing a session token",
            )
        claims = _require_matching_ticket(
            session_ticket,
            channel=channel,
            uid=uid,
            require_agent_id=True,
        )
        channel_name = channel
        user_uid = uid
        agent_uid = claims["agent_uid"]
        ticket = session_ticket

    try:
        app_id = os.getenv("AGORA_APP_ID")
        app_certificate = os.getenv("AGORA_APP_CERTIFICATE")
        if not app_id or not app_certificate:
            raise RuntimeError("Agora credentials are not configured")

        token = generate_convo_ai_token(
            app_id=app_id,
            app_certificate=app_certificate,
            channel_name=channel_name,
            uid=user_uid,
            token_expire=TOKEN_TTL_SECONDS,
        )
        return {
            "code": 0,
            "data": {
                "app_id": app_id,
                "token": token,
                "uid": str(user_uid),
                "channel_name": channel_name,
                "agent_uid": str(agent_uid),
                "session_ticket": ticket,
            },
            "msg": "success",
        }
    except Exception as exc:
        _log_route_error("/get_config", exc, channel=channel_name, uid=user_uid)
        raise _to_http_error(exc)


@router.post("/startAgent")
async def start_agent(request: StartAgentRequest):
    """Start an agent only for the session initialized by this server."""
    if agent is None:
        raise HTTPException(
            status_code=500,
            detail="Service not properly configured. Check server environment variables.",
        )

    claims = _require_matching_ticket(
        request.sessionTicket,
        channel=request.channelName,
        uid=request.userUid,
        require_agent_id=False,
    )
    if request.rtcUid != claims["agent_uid"]:
        raise HTTPException(status_code=403, detail="Session ticket does not match this agent")

    output_audio_codec = None
    if request.parameters:
        output_audio_codec = request.parameters.get("output_audio_codec")

    ticket_id = claims["ticket_id"]
    _prune_expired_started_sessions()
    start_lock = _start_locks.setdefault(ticket_id, asyncio.Lock())
    try:
        async with start_lock:
            previous = _started_sessions.get(ticket_id)
            if previous:
                if previous["stopped"]:
                    raise HTTPException(status_code=409, detail="Agent session has already stopped")
                result = dict(previous["result"])
            else:
                result = await agent.start(
                    channel_name=request.channelName,
                    agent_uid=request.rtcUid,
                    user_uid=request.userUid,
                    output_audio_codec=output_audio_codec,
                )
                claims["agent_id"] = result["agent_id"]
                result["session_ticket"] = _create_session_ticket(claims)
                _started_sessions[ticket_id] = {
                    "result": dict(result),
                    "stopped": False,
                    "expires_at": claims["expires_at"],
                }
        return {"code": 0, "msg": "success", "data": result}
    except HTTPException:
        raise
    except Exception as exc:
        _log_route_error(
            "/startAgent",
            exc,
            channel=request.channelName,
            agent_uid=request.rtcUid,
            user_uid=request.userUid,
        )
        raise _to_http_error(exc)


@router.post("/stopAgent")
async def stop_agent(request: StopAgentRequest):
    """Stop only the agent ID bound into the signed session ticket."""
    if agent is None:
        raise HTTPException(
            status_code=500,
            detail="Service not properly configured. Check server environment variables.",
        )

    claims = _require_matching_ticket(
        request.sessionTicket,
        channel=request.channelName,
        uid=request.userUid,
        require_agent_id=True,
        allow_expired=True,
    )
    if request.agentId != claims["agent_id"]:
        raise HTTPException(status_code=403, detail="Session ticket does not match this agent")

    try:
        await agent.stop(request.agentId)
        started = _started_sessions.get(claims["ticket_id"])
        if started:
            started["stopped"] = True
        return {"code": 0, "msg": "success"}
    except HTTPException:
        raise
    except Exception as exc:
        _log_route_error("/stopAgent", exc, agent_id=request.agentId)
        raise _to_http_error(exc)


app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
