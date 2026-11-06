const API_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

async function request(path, signal) {
  let response
  try { response = await fetch(`${API_URL}${path}`, { signal }) }
  catch (cause) {
    if (cause.name === 'AbortError') throw cause
    const error = new Error('The FastAPI service could not be reached')
    error.status = 0
    throw error
  }
  if (!response.ok) {
    const error = new Error(`Request failed with status ${response.status}`)
    error.status = response.status
    throw error
  }
  return response.json()
}

export function fetchJobs(filters = {}, { page = 1, pageSize = 20, signal } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  for (const key of ['keyword', 'company', 'location', 'source', 'employment_type', 'workplace_type']) {
    if (filters[key]?.trim()) params.set(key, filters[key].trim())
  }
  return request(`/jobs?${params}`, signal)
}
export function fetchJob(jobId) { return request(`/jobs/${jobId}`) }
export { API_URL }
