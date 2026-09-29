import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { Status, Turn } from '../types'

const STATE_TEXT: Record<Status, string> = {
  idle: 'Tap to speak',
  listening: 'Listening',
  transcribing: 'Understanding',
  understanding: 'Understanding',
  responding: 'Responding',
  analysing: 'Finding your pathway',
}

type Props = {
  connected: boolean
  active: boolean
  status: Status
  level: number
  levels: number[]
  greeting: string
  transcript: Turn[]
  demoMode: boolean
  onToggle: () => void
  onSend: (text: string) => void
  onSample: () => void
}

export default function VoicePanel(p: Props) {
  const [typing, setTyping] = useState(false)
  const [draft, setDraft] = useState('')
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [p.transcript.length])

  const listening = p.status === 'listening'
  const working = p.status !== 'idle' && !listening
  const label = !p.connected ? 'Connecting…' : !p.active && p.status === 'idle' ? STATE_TEXT.idle : STATE_TEXT[p.status]

  const submit = () => {
    if (!draft.trim()) return
    p.onSend(draft.trim())
    setDraft('')
  }

  return (
    <section className="card flex flex-col min-h-0 p-6">
      <div className="eyebrow">Voice</div>

      <div className="flex flex-col items-center pt-6 pb-4">
        <div className="relative h-32 w-32 flex items-center justify-center">
          {listening && (
            <motion.div
              className="absolute inset-0 rounded-full bg-leaf-100"
              animate={{ scale: 1 + Math.min(p.level, 1) * 0.35 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            />
          )}
          {working && (
            <motion.div
              className="absolute inset-1 rounded-full border-[3px] border-navy-100 border-t-navy"
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1.1, ease: 'linear' }}
            />
          )}
          <button
            onClick={p.onToggle}
            disabled={!p.connected}
            aria-label={p.active ? 'Stop listening' : 'Start speaking'}
            className={`relative h-24 w-24 rounded-full flex items-center justify-center text-white transition-colors shadow-lift
              disabled:opacity-40 focus:outline-none focus-visible:ring-4 focus-visible:ring-navy-100
              ${listening ? 'bg-leaf' : 'bg-navy hover:bg-navy-600'}`}
          >
            {p.active ? <StopIcon /> : <MicIcon />}
          </button>
        </div>

        <div className="mt-4 text-xl font-semibold text-ink" aria-live="polite">{label}</div>
        <div className="mt-3 flex h-10 items-center gap-[3px]" aria-hidden>
          {p.levels.map((v, i) => (
            <div
              key={i}
              className={`w-[4px] rounded-full transition-all duration-100 ${listening ? 'bg-leaf' : 'bg-line'}`}
              style={{ height: `${Math.max(4, Math.min(1, (listening ? v : 0) * 1.4) * 40)}px` }}
            />
          ))}
        </div>
      </div>

      <div ref={logRef} className="thin-scroll flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
        {p.transcript.length === 0 && (
          <p className="text-center text-ink-muted text-[15px] leading-relaxed px-4">
            {p.greeting || 'Tell us about your work and what you are hoping for.'}
          </p>
        )}
        <AnimatePresence initial={false}>
          {p.transcript.map((t, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex ${t.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[88%] rounded-2xl px-4 py-2.5 text-[15px] leading-snug
                  ${t.role === 'user' ? 'bg-navy-50 text-ink rounded-br-md' : 'bg-white border border-line text-ink-soft rounded-bl-md'}`}
              >
                <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint mb-0.5">
                  {t.role === 'user' ? 'Beneficiary' : 'Guide'}
                </div>
                {t.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="pt-4 mt-2 border-t border-line-soft">
        {typing ? (
          <form className="flex gap-2" onSubmit={e => { e.preventDefault(); submit() }}>
            <input
              autoFocus
              value={draft}
              onChange={e => setDraft(e.target.value)}
              placeholder="Type what you would say…"
              className="flex-1 rounded-xl border border-line px-3 py-2 text-sm focus:outline-none focus:border-navy"
            />
            <button type="submit" className="rounded-xl bg-navy px-4 text-sm font-medium text-white disabled:opacity-40" disabled={!draft.trim()}>
              Send
            </button>
          </form>
        ) : (
          <div className="flex items-center justify-between text-sm">
            <button onClick={() => setTyping(true)} className="text-ink-muted hover:text-navy">Type instead</button>
            {p.demoMode && !p.active && p.status === 'idle' && (
              <button onClick={p.onSample} className="text-ink-muted hover:text-navy">Play recorded sample</button>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

function MicIcon() {
  return (
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="2.5" />
    </svg>
  )
}
