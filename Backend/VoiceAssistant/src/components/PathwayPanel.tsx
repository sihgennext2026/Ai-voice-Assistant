import { motion } from 'framer-motion'
import type { Opportunity, Pathway } from '../types'

const reveal = (i: number) => ({
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  transition: { delay: 0.15 + i * 0.18, duration: 0.45, ease: 'easeOut' as const },
})

export default function PathwayPanel({ pathway, analysing }: { pathway: Pathway | null; analysing: boolean }) {
  if (!pathway) return <EmptyState analysing={analysing} />
  const { best, alternatives } = pathway

  return (
    <section className="card flex flex-col min-h-0 overflow-y-auto thin-scroll p-6">
      <motion.div {...reveal(0)} className="flex items-start justify-between gap-4">
        <div>
          <div className="eyebrow text-leaf">Best-fit livelihood pathway</div>
          <h2 className="mt-1.5 text-[34px] font-bold leading-tight text-navy">{best.pathway}</h2>
          <p className="mt-1 text-[15px] text-ink-muted">{best.outcome}</p>
        </div>
        <FitScore score={best.fit_score} />
      </motion.div>

      <motion.ol {...reveal(1)} className="mt-6 grid grid-cols-3 gap-2">
        {best.stages.map((stage, i) => (
          <li key={stage.key} className="relative rounded-xl border border-navy-100 bg-navy-50/60 px-3.5 py-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-navy-600">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-navy text-[11px] text-white">{i + 1}</span>
              {capitalise(stage.key)}
            </div>
            <div className="mt-2 text-[15px] font-semibold leading-snug text-ink">{stage.label}</div>
            {stage.detail && <div className="mt-1 text-xs leading-snug text-ink-muted">{stage.detail}</div>}
            {i < best.stages.length - 1 && (
              <span className="absolute -right-2.5 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white text-navy" aria-hidden>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 6l6 6-6 6" />
                </svg>
              </span>
            )}
          </li>
        ))}
      </motion.ol>

      <motion.ul {...reveal(2)} className="mt-5 grid grid-cols-2 gap-x-4 gap-y-2">
        {best.highlights.map(h => (
          <li key={h} className="flex items-center gap-2 text-[15px] font-medium text-ink">
            <span className="flex h-5 w-5 flex-none items-center justify-center rounded-full bg-leaf-50 text-leaf">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
            </span>
            {h}
          </li>
        ))}
      </motion.ul>

      <motion.div {...reveal(3)} className="mt-5 grid grid-cols-2 gap-3">
        <InfoBox label="Skill gap" value={best.skill_gap.length ? best.skill_gap.map(capitalise).join(', ') : 'None identified'} tone="saffron" />
        <InfoBox label="Next step" value={best.next_step} tone="leaf" />
      </motion.div>

      {best.opportunities.length > 0 && (
        <motion.div {...reveal(4)} className="mt-5">
          <div className="eyebrow mb-2">Local opportunity</div>
          <ul className="divide-y divide-line-soft rounded-xl border border-line">
            {best.opportunities.map(o => <OpportunityRow key={o.id} o={o} />)}
          </ul>
        </motion.div>
      )}

      <motion.div {...reveal(5)} className="mt-auto pt-5 text-xs leading-relaxed text-ink-faint">
        {alternatives.length > 0 && (
          <div className="mb-1">
            Also considered: {alternatives.map(a => `${a.pathway} (${a.fit_score})`).join(' · ')}
          </div>
        )}
        Scores and eligibility are computed by transparent rules, not by the AI. {best.data_note}.
      </motion.div>
    </section>
  )
}

function FitScore({ score }: { score: number }) {
  const r = 30
  const c = 2 * Math.PI * r
  return (
    <div className="relative h-[76px] w-[76px] flex-none" aria-label={`Fit score ${score} out of 100`}>
      <svg viewBox="0 0 76 76" className="h-full w-full -rotate-90">
        <circle cx="38" cy="38" r={r} fill="none" stroke="#E8F5F0" strokeWidth="7" />
        <motion.circle
          cx="38" cy="38" r={r} fill="none" stroke="#0F7B5F" strokeWidth="7" strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - score / 100) }}
          transition={{ delay: 0.3, duration: 1.1, ease: 'easeOut' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[22px] font-bold leading-none text-ink">{score}</span>
        <span className="text-[10px] font-medium uppercase tracking-wider text-ink-muted">Fit</span>
      </div>
    </div>
  )
}

function InfoBox({ label, value, tone }: { label: string; value: string; tone: 'saffron' | 'leaf' }) {
  const styles = tone === 'saffron' ? 'bg-saffron-50 border-[#F5DDBF]' : 'bg-leaf-50 border-leaf-100'
  return (
    <div className={`rounded-xl border px-4 py-3 ${styles}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
      <div className="mt-1 text-[15px] font-semibold text-ink">{value}</div>
    </div>
  )
}

function OpportunityRow({ o }: { o: Opportunity }) {
  const osm = o.source.startsWith('openstreetmap')
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold text-ink">{o.name}</div>
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <span className="truncate">{o.area}</span>
          <span className={`source-tag ${osm ? 'border-navy-100 text-navy-600' : 'border-[#F5DDBF] text-saffron'}`}>
            {osm ? 'OpenStreetMap' : 'Illustrative'}
          </span>
        </div>
      </div>
      <div className="text-right">
        <div className={`text-[15px] font-semibold ${o.within_reach ? 'text-ink' : 'text-saffron'}`}>
          {o.distance_km != null ? `${o.distance_km} km` : '—'}
        </div>
        <div className="text-[11px] text-ink-faint">
          {o.duration_min != null ? `${o.duration_min} min drive` : o.distance_source === 'straight-line' ? 'nearest' : o.distance_source}
        </div>
      </div>
    </li>
  )
}

function EmptyState({ analysing }: { analysing: boolean }) {
  return (
    <section className="card flex flex-col items-center justify-center p-10 text-center">
      <svg width="148" height="44" viewBox="0 0 148 44" fill="none" aria-hidden>
        <path d="M12 22 H136" stroke="#DCE8F6" strokeWidth="3" strokeDasharray="6 7" strokeLinecap="round" />
        {[12, 74, 136].map((x, i) => (
          <motion.circle
            key={x} cx={x} cy="22" r="9" fill={i === 2 ? '#E8F5F0' : '#EEF4FB'} stroke={i === 2 ? '#0F7B5F' : '#0B3B6F'} strokeWidth="2.5"
            animate={analysing ? { scale: [1, 1.2, 1] } : {}}
            transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.25 }}
          />
        ))}
      </svg>
      <div className="mt-5 text-lg font-semibold text-ink">{analysing ? 'Matching your profile…' : 'Your pathway will appear here'}</div>
      <p className="mt-1.5 max-w-xs text-[15px] text-ink-muted">
        Training, a nearby opportunity, and the livelihood it leads to.
      </p>
    </section>
  )
}

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
