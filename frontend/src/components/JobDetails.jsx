import { CalendarDays, ExternalLink, MapPin, X } from 'lucide-react'

function formatDate(value) {
  if (!value) return 'Date unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en', { dateStyle: 'long' }).format(date)
}

export default function JobDetails({ job, onClose }) {
  if (!job) return null
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="details-modal" role="dialog" aria-modal="true" aria-labelledby="job-detail-title">
      <button className="close-button" onClick={onClose} aria-label="Close job details"><X size={19} /></button>
      <p className="eyebrow">{job.source}{job.source_board ? ` / ${job.source_board}` : ''}</p><h2 id="job-detail-title">{job.title || 'Untitled role'}</h2><p className="detail-company">{job.company || 'Unknown company'}</p>
      <div className="detail-list"><span><MapPin size={17} /> {job.location || 'Location unavailable'}</span><span><CalendarDays size={17} /> Posted {formatDate(job.posted_date)}</span></div>
      <p>{job.employment_type || 'Employment type unavailable'} · {job.workplace_type || 'Workplace unavailable'}</p>
      <p>{job.salary || 'Compensation unavailable'} {job.salary_currency || ''}</p>
      <p>First seen {formatDate(job.first_seen_at)} · Last seen {formatDate(job.last_seen_at)}</p>
      <p className="job-description">{job.description || 'Description unavailable. See the original listing.'}</p>
      <div className="detail-footer"><p>Source listing<br /><strong>{job.url || 'No URL provided'}</strong></p>{job.url && <a className="button button-primary" href={job.apply_url || job.job_url || job.url} target="_blank" rel="noopener noreferrer">View / apply <ExternalLink size={16} /></a>}</div>
    </section>
  </div>
}
