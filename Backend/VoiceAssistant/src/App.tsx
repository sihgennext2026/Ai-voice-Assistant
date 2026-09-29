import { motion } from 'framer-motion'
import PathwayPanel from './components/PathwayPanel'
import ProfilePanel from './components/ProfilePanel'
import VoicePanel from './components/VoicePanel'
import type { AgentState } from './types'
import { useAgent } from './useAgent'

const PRODUCT_NAME = 'RoziRaah'
const JOURNEY = ['Voice', 'Understand', 'Profile', 'Match', 'Pathway', 'Livelihood']

function journeyStage(s: AgentState): number {
  if (s.pathway) return 5
  if (s.analysis) return 3
  if (s.profile.some(f => f.key !== 'location')) return 2
  if (s.transcript.length) return 1
  return s.active || s.status === 'listening' ? 0 : -1
}

export default function App() {
  const { state, toggleMic, sendText, reset, runSample } = useAgent()
  const stage = journeyStage(state)
  const demoMode = !!state.caps?.demo_mode

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-line bg-white px-8 py-4">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <div className="text-lg font-bold leading-tight text-navy">{PRODUCT_NAME}</div>
            <div className="text-[13px] text-ink-muted">Tell us your story. We identify a realistic path to livelihood.</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {demoMode && (
            <span className="rounded-full border border-line px-3 py-1 font-medium text-ink-muted">Demo case · Sanganer, Jaipur</span>
          )}
          <span className={`flex items-center gap-1.5 rounded-full px-3 py-1 font-medium ${state.connected ? 'bg-leaf-50 text-leaf' : 'bg-saffron-50 text-saffron'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${state.connected ? 'bg-leaf' : 'bg-saffron'}`} />
            {state.connected ? 'Online' : 'Connecting'}
          </span>
          <button onClick={reset} className="rounded-full border border-line px-3 py-1 font-medium text-ink-soft hover:border-navy hover:text-navy">
            New conversation
          </button>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-12 gap-5 px-8 py-6">
        <div className="col-span-4 flex min-h-0 flex-col">
          <VoicePanel
            connected={state.connected}
            active={state.active}
            status={state.status}
            level={state.level}
            levels={state.levels}
            greeting={state.greeting}
            transcript={state.transcript}
            demoMode={demoMode}
            onToggle={toggleMic}
            onSend={sendText}
            onSample={runSample}
          />
        </div>
        <div className="col-span-3 flex min-h-0 flex-col">
          <ProfilePanel profile={state.profile} changed={state.changed} analysis={state.analysis} />
        </div>
        <div className="col-span-5 flex min-h-0 flex-col">
          <PathwayPanel pathway={state.pathway} analysing={!!state.analysis && !state.pathway} />
        </div>
      </main>

      <footer className="border-t border-line bg-white px-8 py-3.5">
        <ol className="flex items-center justify-center gap-2">
          {JOURNEY.map((step, i) => {
            const reached = i <= stage
            const current = i === stage || (stage === 5 && i === 4)
            return (
              <li key={step} className="flex items-center gap-2">
                <motion.span
                  animate={{ opacity: reached ? 1 : 0.45 }}
                  className={`rounded-full px-3.5 py-1 text-[13px] font-semibold transition-colors
                    ${reached ? (i === 5 ? 'bg-leaf text-white' : current ? 'bg-navy text-white' : 'bg-navy-50 text-navy') : 'text-ink-faint'}`}
                >
                  {step}
                </motion.span>
                {i < JOURNEY.length - 1 && <span className={`h-px w-8 ${i < stage ? 'bg-navy' : 'bg-line'}`} />}
              </li>
            )
          })}
        </ol>
      </footer>
    </div>
  )
}

function Logo() {
  return (
    <svg width="38" height="38" viewBox="0 0 40 40" aria-hidden>
      <rect width="40" height="40" rx="11" fill="#0B3B6F" />
      <path d="M11 28 C15 28 16 20 20 20 S25 12 29 12" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <circle cx="11" cy="28" r="2.8" fill="#fff" />
      <circle cx="29" cy="12" r="3.2" fill="#6FD3AE" />
    </svg>
  )
}
