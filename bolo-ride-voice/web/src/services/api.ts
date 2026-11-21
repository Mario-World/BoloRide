const API_BASE_URL = '/api'

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
  const response = await fetch(`${API_BASE_URL}/get_config${query ? `?${query}` : ''}`, {
    method: 'GET',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  const result = await response.json()
  if (result.code !== 0 || !result.data) {
    throw new Error(result.msg || 'Failed to get configuration')
  }
  return result.data
}

export async function startAgent(
  channelName: string,
  rtcUid: number,
  userUid: number,
  sessionTicket: string,
): Promise<AgentStartResponse> {
  const payload = { channelName, rtcUid, userUid, sessionTicket }

  const response = await fetch(`${API_BASE_URL}/startAgent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  const result = await response.json()
  if (result.code !== 0 || !result.data?.agent_id || !result.data?.session_ticket) {
    throw new Error(result.msg || 'Failed to start agent')
  }
  return {
    agent_id: result.data.agent_id,
    session_ticket: result.data.session_ticket,
  }
}

export async function stopAgent(
  agentId: string,
  channelName: string,
  userUid: number,
  sessionTicket: string,
): Promise<void> {
  if (!agentId) return

  const response = await fetch(`${API_BASE_URL}/stopAgent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agentId, channelName, userUid, sessionTicket }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
}
