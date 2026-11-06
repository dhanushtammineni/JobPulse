import { useEffect, useState } from 'react'
import { Database, Filter, Layers3, RefreshCw } from 'lucide-react'
import Header from './components/Header'
import SearchFilters from './components/SearchFilters'
import JobCard from './components/JobCard'
import JobDetails from './components/JobDetails'
import Pagination from './components/Pagination'
import AnalyticsDashboard from './components/AnalyticsDashboard'
import { EmptyState, ErrorState, LoadingState } from './components/States'
import { fetchJobs } from './services/api'

const initialFilters = { keyword: '', company: '', location: '', source: '', employment_type: '', workplace_type: '' }

export default function App() {
  const [filters, setFilters] = useState(initialFilters)
  const [submittedFilters, setSubmittedFilters] = useState(initialFilters)
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedJob, setSelectedJob] = useState(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(6)
  const [total, setTotal] = useState(0)
  const [ingestion, setIngestion] = useState([])
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetchJobs(submittedFilters, { page, pageSize, signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) {
          setJobs(result.items)
          setTotal(result.total)
          setIngestion(result.ingestion)
          if (page > 1 && result.total > 0 && result.items.length === 0) setPage(1)
        }
      })
      .catch((requestError) => { if (!controller.signal.aborted) setError(requestError) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [submittedFilters, page, pageSize, reload])

  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const successful = ingestion.filter((run) => run.status === 'succeeded' && run.finished_at)
  const lastSync = successful.map((run) => run.finished_at).sort().at(-1)
  const failed = ingestion.filter((run) => run.status === 'failed')
  const refresh = () => setReload((value) => value + 1)

  const updateFilter = (name, value) => setFilters((current) => ({ ...current, [name]: value }))
  const handleSubmit = (event) => { event.preventDefault(); setSubmittedFilters(filters); setPage(1); refresh() }
  const clearFilters = () => { setFilters(initialFilters); setSubmittedFilters(initialFilters); setPage(1); refresh() }
  const changePageSize = (value) => { setPageSize(value); setPage(1) }

  return <div id="top" className="app-shell">
    <Header />
    <main>
      <SearchFilters filters={filters} onChange={updateFilter} onSubmit={handleSubmit} onClear={clearFilters} loading={loading} />
      <section className="jobs-section" id="jobs">
        <div className="section-heading"><div><p className="eyebrow">Job index</p><h2>Latest opportunities <span className="result-count">{loading ? '...' : total}</span></h2></div><div className="section-tools"><span className="sync-label"><RefreshCw size={14} /> {lastSync ? `Last completed ingestion: ${new Date(lastSync).toLocaleString()}` : 'No completed ingestion recorded'}</span><span className="filter-label"><Filter size={14} /> {Object.values(submittedFilters).some(Boolean) ? 'Filtered view' : 'All roles'}</span></div></div>
        {failed.length > 0 && <p role="status">Some sources could not refresh: {failed.map((run) => `${run.source}/${run.source_board}`).join(', ')}. Previously collected jobs remain available.</p>}
        {loading ? <LoadingState /> : error ? <ErrorState onRetry={refresh} /> : total === 0 ? <EmptyState onClear={clearFilters} /> : <>
          <div className="job-list">{jobs.map((job, index) => <JobCard key={`${job.url}-${index}`} job={job} onSelect={setSelectedJob} />)}</div>
          <Pagination page={page} pageCount={pageCount} onPageChange={setPage} pageSize={pageSize} onPageSizeChange={changePageSize} />
        </>}
      </section>
      <AnalyticsDashboard visibleJobs={jobs} />
    </main>
    <footer><span><span className="footer-mark"><Layers3 size={14} /></span> JobPulse</span><span><Database size={14} /> Listings served by FastAPI</span></footer>
    <JobDetails job={selectedJob} onClose={() => setSelectedJob(null)} />
  </div>
}
