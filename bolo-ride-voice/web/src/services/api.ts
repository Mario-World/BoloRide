const API_BASE_URL = '/api'

export type VoiceLanguage = 'en' | 'hi' | 'kn' | 'te'

const backendSetupHint =
  'Start the Python voice service on port 8000 and confirm AGENT_BACKEND_URL points to it.'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function requiredString(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`The voice service response is missing ${fieldName}.`)
  }
  return value
}

function getErrorMessage(payload: unknown, status: number): string {
  if (isRecord(payload)) {
    const detail = payload.detail
    if (typeof detail === 'string') return detail
    if (isRecord(detail) && typeof detail.message === 'string') return detail.message
    if (typeof payload.msg === 'string') return payload.msg
  }
  return `The voice service returned HTTP ${status}.`
}

async function requestApiJson(url: string, init?: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    throw new Error(`Could not reach the voice service. ${backendSetupHint}`, { cause: error })
  }

  const body = await response.text()
  let payload: unknown
  try {
    payload = body ? JSON.parse(body) : null
  } catch (error) {
    throw new Error(
      `The voice service returned a non-JSON response (HTTP ${response.status}). ${backendSetupHint}`,
      { cause: error },
    )
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(payload, response.status))
  }
  return payload
}

export interface GetConfigResponse {
  app_id: string
  token: string
  uid: string
  channel_name: string
  agent_uid: string
  session_ticket: string
}

export interface AgentStartResponse {
  agent_id: string
  session_ticket: string
}

export async function getConfig(options?: {
  channel?: string
  uid?: string | number
  sessionTicket?: string
}): Promise<GetConfigResponse> {
  const params = new URLSearchParams()
  if (options?.channel !== undefined && options.channel !== '') {
    params.set('channel', options.channel)
  }
  if (options?.uid !== undefined && options.uid !== '') {
    params.set('uid', String(options.uid))
  }
  if (options?.sessionTicket) {
    params.set('session_ticket', options.sessionTicket)
  }

  const query = params.toString()
  const result = await requestApiJson(`${API_BASE_URL}/get_config${query ? `?${query}` : ''}`, {
    method: 'GET',
  })
  if (!isRecord(result) || result.code !== 0 || !isRecord(result.data)) {
    throw new Error(isRecord(result) && typeof result.msg === 'string' ? result.msg : 'Failed to get configuration')
  }
  return {
    app_id: requiredString(result.data.app_id, 'app_id'),
    token: requiredString(result.data.token, 'token'),
    uid: requiredString(result.data.uid, 'uid'),
    channel_name: requiredString(result.data.channel_name, 'channel_name'),
    agent_uid: requiredString(result.data.agent_uid, 'agent_uid'),
    session_ticket: requiredString(result.data.session_ticket, 'session_ticket'),
  }
}

export async function startAgent(
  channelName: string,
  rtcUid: number,
  userUid: number,
  sessionTicket: string,
  language: VoiceLanguage = 'en',
): Promise<AgentStartResponse> {
  const payload = { channelName, rtcUid, userUid, sessionTicket, language }

  const result = await requestApiJson(`${API_BASE_URL}/startAgent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!isRecord(result) || result.code !== 0 || !isRecord(result.data)) {
    throw new Error(isRecord(result) && typeof result.msg === 'string' ? result.msg : 'Failed to start agent')
  }
  return {
    agent_id: requiredString(result.data.agent_id, 'agent_id'),
    session_ticket: requiredString(result.data.session_ticket, 'session_ticket'),
  }
}

export async function stopAgent(
  agentId: string,
  channelName: string,
  userUid: number,
  sessionTicket: string,
): Promise<void> {
  if (!agentId) return

  await requestApiJson(`${API_BASE_URL}/stopAgent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agentId, channelName, userUid, sessionTicket }),
  })
}
