import { useState } from 'react'
import './App.css'
import { runQuery, type Dataset, type QueryResponse } from './api'
import { AllergenMatrix } from './components/AllergenMatrix'
import { RecommendationList } from './components/RecommendationList'

const EXAMPLE_QUERIES = [
  'Can I eat the flapjack?',
  'Show me which dishes contain nuts or milk',
  'Recommend a lunch under £5 with no wheat',
  'What does "may contain traces" actually mean?',
]

/** Root component: the query form, results view, and "under the hood" debug panel. */
function App() {
  const [allergyOrDiet, setAllergyOrDiet] = useState('peanuts')
  const [query, setQuery] = useState('')
  const [dataset, setDataset] = useState<Dataset>('messy')
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Submits the current form state to the backend and updates the results view. */
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const response = await runQuery(query, allergyOrDiet, dataset)
      setResult(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Can I eat this?</h1>
        <p>An AI dining safety assistant for the thirty-second decision at the counter.</p>
      </header>

      <form className="query-form" onSubmit={handleSubmit}>
        <label>
          Menu data source
          <select value={dataset} onChange={(e) => setDataset(e.target.value as Dataset)}>
            <option value="messy">Messy real-world menu (10 dishes, from the brief)</option>
            <option value="clean">Clean, complete menu (50 dishes)</option>
          </select>
        </label>
        <label>
          Allergy or dietary need
          <input
            type="text"
            value={allergyOrDiet}
            onChange={(e) => setAllergyOrDiet(e.target.value)}
            placeholder="e.g. peanuts, coeliac, vegan"
          />
        </label>
        <label>
          Your question
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Can I eat the flapjack?"
            rows={2}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Checking…' : 'Ask'}
        </button>
        <div className="examples">
          {EXAMPLE_QUERIES.map((example) => (
            <button
              key={example}
              type="button"
              className="example-chip"
              onClick={() => setQuery(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      {error && <div className="card card--error">{error}</div>}

      {result && (
        <div className="results">
          {result.answer && (
            <div className="card">
              <div className="card-header">
                <h3>Answer</h3>
              </div>
              <p>{result.answer}</p>
            </div>
          )}

          {result.safety && <AllergenMatrix safety={result.safety} />}

          {result.recommendations && result.recommendations.length > 0 && (
            <RecommendationList recommendations={result.recommendations} />
          )}

          <details className="under-the-hood">
            <summary>Under the hood</summary>
            <dl>
              <dt>Menu data source</dt>
              <dd>{result.dataset === 'messy' ? 'Messy real-world menu' : 'Clean, complete menu'}</dd>
              <dt>Intents</dt>
              <dd>{result.intents.join(', ')}</dd>
              <dt>Retrieval used</dt>
              <dd>{result.retrieval_used.join(', ')}</dd>
              {result.generated_sql && (
                <>
                  <dt>Generated SQL</dt>
                  <dd>
                    <code>{result.generated_sql}</code>
                  </dd>
                </>
              )}
              {result.retrieved_notes.length > 0 && (
                <>
                  <dt>Kitchen notes retrieved (RAG)</dt>
                  <dd>
                    <ul>
                      {result.retrieved_notes.map((note) => (
                        <li key={note.id}>
                          <strong>{note.title}</strong> ({note.score.toFixed(2)}): {note.text}
                        </li>
                      ))}
                    </ul>
                  </dd>
                </>
              )}
            </dl>
          </details>
        </div>
      )}
    </div>
  )
}

export default App
