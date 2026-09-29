export type Status = 'idle' | 'listening' | 'transcribing' | 'understanding' | 'responding' | 'analysing'

export type Turn = { role: 'user' | 'assistant'; text: string }

export type ProfileField = { key: string; label: string; value: string }

export type StepState = 'pending' | 'active' | 'done'
export type AnalysisStep = { key: string; label: string; state: StepState; detail?: string | null }

export type Opportunity = {
  id: string
  type: string
  name: string
  area: string
  distance_km: number | null
  duration_min: number | null
  distance_source: string
  source: string
  within_reach: boolean
}

export type Stage = { key: string; label: string; detail?: string | null }

export type PathwayMatch = {
  pathway_id: string
  pathway: string
  fit_score: number
  skill_fit: string
  eligibility: string
  travel_fit: string
  skill_gap: string[]
  next_step: string
  outcome: string
  stages: Stage[]
  highlights: string[]
  opportunities: Opportunity[]
  data_note: string
}

export type Alternative = { pathway: string; fit_score: number; travel_fit: string }

export type Pathway = { best: PathwayMatch; alternatives: Alternative[] }

export type Capabilities = { demo_mode: boolean; llm: string[]; tts: string | null; asr: string; ready: boolean }

export type AgentState = {
  connected: boolean
  active: boolean
  status: Status
  level: number
  levels: number[]
  caps: Capabilities | null
  greeting: string
  transcript: Turn[]
  profile: ProfileField[]
  changed: string[]
  analysis: AnalysisStep[] | null
  pathway: Pathway | null
}
