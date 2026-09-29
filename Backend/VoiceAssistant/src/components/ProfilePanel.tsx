import { AnimatePresence, motion } from 'framer-motion'
import type { AnalysisStep, ProfileField } from '../types'

const SLOTS: { key: string; label: string }[] = [
  { key: 'aspiration', label: 'Goal' },
  { key: 'skills', label: 'Skills' },
  { key: 'experience', label: 'Experience' },
  { key: 'education', label: 'Education' },
  { key: 'formal_training', label: 'Training' },
  { key: 'mobility', label: 'Constraint' },
  { key: 'preferred_work', label: 'Preferred work' },
  { key: 'location', label: 'Location' },
]

type Props = { profile: ProfileField[]; changed: string[]; analysis: AnalysisStep[] | null }

export default function ProfilePanel({ profile, changed, analysis }: Props) {
  const values = Object.fromEntries(profile.map(f => [f.key, f.value]))
  const known = profile.length

  return (
    <section className="card flex flex-col min-h-0 p-6">
      <div className="flex items-baseline justify-between">
        <div className="eyebrow">Livelihood profile</div>
        <div className="text-xs text-ink-faint">{known ? `${known} understood` : 'From conversation'}</div>
      </div>

      <dl className="mt-4 divide-y divide-line-soft">
        {SLOTS.map(slot => {
          const value = values[slot.key]
          const fresh = changed.includes(slot.key)
          return (
            <div key={slot.key} className="relative flex items-center justify-between gap-4 py-2.5">
              {fresh && (
                <motion.div
                  key={value}
                  className="absolute -inset-x-3 inset-y-0.5 rounded-lg bg-leaf-50"
                  initial={{ opacity: 1 }}
                  animate={{ opacity: 0 }}
                  transition={{ duration: 2.4, ease: 'easeOut' }}
                />
              )}
              <dt className="relative text-[12px] font-semibold uppercase tracking-wider text-ink-muted">{slot.label}</dt>
              <dd className="relative text-right text-[15px]">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span
                    key={value ?? 'empty'}
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    className={value ? 'font-semibold text-ink' : 'text-ink-faint'}
                  >
                    {value ?? '—'}
                  </motion.span>
                </AnimatePresence>
              </dd>
            </div>
          )
        })}
      </dl>

      <AnimatePresence>
        {analysis && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-6 pt-5 border-t border-line">
            <div className="eyebrow mb-3">Analysis</div>
            <ol className="space-y-2.5">
              {analysis.map(step => (
                <li key={step.key} className="flex items-center gap-3">
                  <StepIcon state={step.state} />
                  <span className={`text-[15px] ${step.state === 'pending' ? 'text-ink-faint' : 'text-ink'}`}>{step.label}</span>
                  {step.state === 'done' && step.detail && (
                    <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="ml-auto text-xs text-ink-muted text-right">
                      {step.detail}
                    </motion.span>
                  )}
                </li>
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

function StepIcon({ state }: { state: AnalysisStep['state'] }) {
  if (state === 'done') {
    return (
      <motion.span initial={{ scale: 0.4 }} animate={{ scale: 1 }} className="flex h-5 w-5 items-center justify-center rounded-full bg-leaf text-white">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      </motion.span>
    )
  }
  if (state === 'active') {
    return (
      <motion.span
        className="h-5 w-5 rounded-full border-2 border-navy-100 border-t-navy"
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 0.8, ease: 'linear' }}
      />
    )
  }
  return <span className="h-5 w-5 rounded-full border-2 border-line" />
}
