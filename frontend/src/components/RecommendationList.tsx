import type { Recommendation } from '../api'

interface RecommendationListProps {
  recommendations: Recommendation[]
}

/** Renders a ranked list of recommended dishes with their reasons. */
export function RecommendationList({ recommendations }: RecommendationListProps) {
  return (
    <div className="card">
      <div className="card-header">
        <h3>Recommendations</h3>
      </div>
      <ol className="recommendation-list">
        {recommendations.map((rec) => (
          <li key={rec.name}>
            <strong>{rec.name}</strong>
            <p>{rec.reason}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
