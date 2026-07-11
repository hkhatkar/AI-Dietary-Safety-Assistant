import type { SafetyResult } from '../api'
import { VerdictBadge } from './VerdictBadge'

const CELL_LABEL: Record<string, string> = {
  contains: 'Contains',
  may_contain: 'May contain',
  not_listed: 'Not listed',
  unknown: 'Unknown',
}

interface AllergenMatrixProps {
  safety: SafetyResult
}

/** Renders a per-dish allergen breakdown table plus an overall verdict badge. */
export function AllergenMatrix({ safety }: AllergenMatrixProps) {
  const allergenNames = Array.from(
    new Set(safety.dishes.flatMap((d) => Object.keys(d.allergens))),
  )

  return (
    <div className="card">
      <div className="card-header">
        <h3>Allergen matrix</h3>
        <VerdictBadge verdict={safety.overall_verdict} />
      </div>
      <div className="table-scroll">
        <table className="matrix">
          <thead>
            <tr>
              <th>Dish</th>
              {allergenNames.map((a) => (
                <th key={a}>{a}</th>
              ))}
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {safety.dishes.map((dish) => (
              <tr key={dish.name}>
                <td>{dish.name}</td>
                {allergenNames.map((a) => (
                  <td key={a} className={`cell cell--${dish.allergens[a] ?? 'unknown'}`}>
                    {CELL_LABEL[dish.allergens[a]] ?? 'Unknown'}
                  </td>
                ))}
                <td>
                  <VerdictBadge verdict={dish.verdict} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="reasoning-list">
        {safety.dishes.map((dish) => (
          <li key={dish.name}>
            <strong>{dish.name}:</strong> {dish.reasoning}
          </li>
        ))}
      </ul>
    </div>
  )
}
