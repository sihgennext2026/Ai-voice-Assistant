import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { AgentState, AnalysisStep, Status } from './types'

export const API_URL = (import.meta.env.NEXT_PUBLIC_API_URL as string | undefined) ?? 'http://localhost:8000'
const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws'

type Event = { type: string; [key: string]: unknown }
type Action = Event | { type: '_connected'; value: boolean }

const initial: AgentState = {
  connected: false,
  active: false,
  status: 'idle',
  level: 0,
  levels: Array(28).fill(0),
  caps: null,
  greeting: '',
  transcript: [],
  profile: [],
  changed: [],
  analysis: null,
  pathway: null,
}

function reducer(state: AgentState, e: Action): AgentState {
  switch (e.type) {
    case '_connected':
      return e.value ? { ...state, connected: true } : { ...state, connected: false, active: false, status: 'idle', level: 0 }
    case 'capabilities':
      return { ...state, caps: e as unknown as AgentState['caps'] }
    case 'session_state': {
      const analysis = e.analysis as AnalysisStep[]
      return {
        ...state,
        greeting: e.greeting as string,
        transcript: e.transcript as AgentState['transcript'],
        profile: e.profile as AgentState['profile'],
        changed: [],
        analysis: analysis.length ? analysis : null,
        pathway: e.pathway as AgentState['pathway'],
      }
    }
    case 'agent_active':
      return { ...state, active: !!e.active, ...(e.active ? {} : { level: 0 }) }
    case 'status':
      return { ...state, status: e.status as Status }
    case 'level':
      return { ...state, level: e.value as number, levels: [...state.levels.slice(1), e.value as number] }
    case 'transcript':
      return { ...state, transcript: [...state.transcript, { role: e.role as 'user' | 'assistant', text: e.text as string }] }
    case 'profile_update':
      return { ...state, profile: e.profile as AgentState['profile'], changed: e.changed as string[] }
    case 'analysis_start':
      return {
        ...state,
        analysis: (e.steps as { key: string; label: string }[]).map(s => ({ ...s, state: 'pending' as const })),
      }
    case 'analysis_step':
      return {
        ...state,
        analysis: (state.analysis ?? []).map(s =>
          s.key === e.key ? { ...s, state: e.state as AnalysisStep['state'], detail: (e.detail as string) ?? s.detail } : s,
        ),
      }
    case 'pathway':
      return { ...state, pathway: { best: e.best, alternatives: e.alternatives } as AgentState['pathway'] }
    default:
      return state
  }
}

export function useAgent() {
  const [state, dispatch] = useReducer(reducer, initial)
  const ws = useRef<WebSocket | null>(null)

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    let closed = false
    const connect = () => {
      const socket = new WebSocket(WS_URL)
      ws.current = socket
      socket.onopen = () => dispatch({ type: '_connected', value: true })
      socket.onmessage = msg => dispatch(JSON.parse(msg.data) as Event)
      socket.onclose = () => {
        dispatch({ type: '_connected', value: false })
        if (!closed) timer = setTimeout(connect, 1500)
      }
      socket.onerror = () => socket.close()
    }
    connect()
    return () => {
      closed = true
      clearTimeout(timer)
      ws.current?.close()
    }
  }, [])

  const post = useCallback((path: string) => fetch(`${API_URL}${path}`, { method: 'POST' }).catch(() => undefined), [])
  const send = useCallback((payload: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(payload))
  }, [])

  return {
    state,
    toggleMic: () => post(state.active ? '/agent/stop' : '/agent/start'),
    sendText: (text: string) => send({ action: 'user_text', text }),
    reset: () => send({ action: 'reset' }),
    runSample: () => post('/demo/run'),
  }
}
