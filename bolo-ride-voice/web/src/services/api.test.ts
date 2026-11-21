import { afterEach, expect, test } from 'bun:test'

import { getConfig, startAgent, stopAgent } from './api'

const originalFetch = globalThis.fetch
let lastCall: { url: string; init?: RequestInit }

afterEach(() => {
  globalThis.fetch = originalFetch
})

function mockFetch(status: number, body: unknown) {
  globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
    lastCall = { url: String(url), init }
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    })
  }) as typeof fetch
}

test('getConfig requests a session-bound token and returns its ticket', async () => {
  mockFetch(200, {
    code: 0,
    msg: 'success',
    data: {
      app_id: 'a',
      token: 't',
      uid: '5',
      channel_name: 'c',
      agent_uid: '9',
      session_ticket: 'signed-session-ticket',
    },
  })
  const data = await getConfig({ channel: 'c', uid: 5, sessionTicket: 'signed-session-ticket' })
  expect(data.token).toBe('t')
  expect(data.session_ticket).toBe('signed-session-ticket')
  expect(lastCall.url).toContain('/api/get_config')
  expect(lastCall.url).toContain('channel=c')
  expect(lastCall.url).toContain('uid=5')
  expect(lastCall.url).toContain('session_ticket=signed-session-ticket')
})

test('startAgent posts the payload and returns agent_id', async () => {
  mockFetch(200, {
    code: 0,
    msg: 'success',
    data: { agent_id: 'agent-1', session_ticket: 'started-session-ticket' },
  })
  const result = await startAgent('ch', 111, 222, 'bootstrap-session-ticket')
  expect(result).toEqual({ agent_id: 'agent-1', session_ticket: 'started-session-ticket' })
  expect(lastCall.url).toContain('/api/startAgent')
  expect(lastCall.init?.method).toBe('POST')
  expect(JSON.parse(String(lastCall.init?.body))).toEqual({
    channelName: 'ch',
    rtcUid: 111,
    userUid: 222,
    sessionTicket: 'bootstrap-session-ticket',
  })
})

test('stopAgent posts the agentId', async () => {
  mockFetch(200, {})
  await stopAgent('agent-1', 'ch', 222, 'started-session-ticket')
  expect(lastCall.url).toContain('/api/stopAgent')
  expect(JSON.parse(String(lastCall.init?.body))).toEqual({
    agentId: 'agent-1',
    channelName: 'ch',
    userUid: 222,
    sessionTicket: 'started-session-ticket',
  })
})

test('getConfig throws on an error response', async () => {
  mockFetch(500, { detail: 'boom' })
  await expect(getConfig()).rejects.toThrow('boom')
})
