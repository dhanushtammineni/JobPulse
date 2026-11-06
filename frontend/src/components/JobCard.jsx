import { ArrowUpRight, CalendarDays, MapPin } from 'lucide-react'

function formatDate(value) {
  if (!value) return 'Date unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

export default function JobCard({ job, onSelect }) {
  return (
    <article className="job-card" onClick={() => onSelect(job)}>
      <div className="company-avatar">{job.company?.slice(0, 1).toUpperCase() || 'J'}</div>
      <div className="job-card-main">
        <p className="eyebrow">{job.source}{job.source_board ? ` / ${job.source_board}` : ''}</p>
        <p className="job-company">{job.company || 'Unknown company'}</p>
        <h3>{job.title || 'Untitled role'}</h3>
        <div className="job-meta"><span><MapPin size={14} /> {job.location || 'Location unavailable'}</span><span><CalendarDays size={14} /> {formatDate(job.posted_date)}</span></div>
        <p>{job.workplace_type || 'Workplace unavailable'} · Last seen {formatDate(job.last_seen_at)}</p>
      </div>
      <button className="icon-button" onClick={(event) => { event.stopPropagation(); onSelect(job) }} aria-label={`View details for ${job.title}`} title="View job details"><ArrowUpRight size={18} /></button>
    </article>
  )
}
