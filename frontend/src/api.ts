/**
 * Types and client for the backend's `/api/query` endpoint. Mirrors `backend/app/schemas.py` -
 * keep the two in sync when the response contract changes.
 */

export type Verdict = 'Safe' | 'Caution' | 'Not safe' | 'Unknown - ask staff'

/** The safety assessment for a single dish. */
export interface DishSafety {
  name: string
  verdict: Verdict
  allergens: Record<string, string>
  reasoning: string
}

/** The safety assessment across one or more dishes, with an overall verdict. */
export interface SafetyResult {
  overall_verdict: Verdict
  dishes: DishSafety[]
}

/** A single recommended dish and why it was recommended. */
export interface Recommendation {
  name: string
  reason: string
}

/** A kitchen policy note returned by semantic search, with its similarity score. */
export interface KitchenNote {
  id: string
  title: string
  text: string
  score: number
}

/** Which seeded menu a query is scoped to. */
export type Dataset = 'messy' | 'clean'

/** The full response body from POST /api/query. */
export interface QueryResponse {
  dataset: Dataset
  intents: string[]
  retrieval_used: string[]
  generated_sql: string | null
  retrieved_notes: KitchenNote[]
  output_types: string[]
  safety: SafetyResult | null
  recommendations: Recommendation[] | null
  answer: string | null
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/**
 * Sends a query to the backend and returns the structured response.
 *
 * @param query - The user's natural-language question.
 * @param allergyOrDiet - The user's declared allergy/diet, if any (blank is sent as null).
 * @param dataset - Which seeded menu to scope the query to.
 * @returns The parsed QueryResponse from the backend.
 * @throws Error if the backend returns a non-2xx status.
 */
export async function runQuery(
  query: string,
  allergyOrDiet: string,
  dataset: Dataset,
): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      allergy_or_diet: allergyOrDiet.trim() || null,
      dataset,
    }),
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`Request failed (${response.status}): ${body}`)
  }

  return response.json()
}
