import type { Verdict } from '../api'

const STYLES: Record<Verdict, string> = {
  Safe: 'verdict verdict--safe',
  Caution: 'verdict verdict--caution',
  'Not safe': 'verdict verdict--not-safe',
  'Unknown - ask staff': 'verdict verdict--unknown',
}

interface VerdictBadgeProps {
  verdict: Verdict
}

/** Renders a colored badge for a safety verdict. */
export function VerdictBadge({ verdict }: VerdictBadgeProps) {
  return <span className={STYLES[verdict] ?? 'verdict'}>{verdict}</span>
}
