import { MapPin, RotateCcw, Search } from 'lucide-react'

export default function SearchFilters({ filters, onChange, onSubmit, onClear, loading }) {
  return (
    <form className="search-panel" onSubmit={onSubmit}>
      <div className="search-heading">
        <div>
          <p className="eyebrow">Opportunity explorer</p>
          <h1>Find your next <em>signal.</em></h1>
          <p className="search-copy">Search the live JobPulse index by company and location.</p>
        </div>
        <span className="live-indicator"><span /> Public job index</span>
      </div>
      <div className="filter-grid">
        <label className="field keyword-field">
          <span>Keyword</span>
          <input value={filters.keyword} onChange={(event) => onChange('keyword', event.target.value)} placeholder="e.g. Data Engineer" />
        </label>
        <label className="field">
          <span>Company</span>
          <input value={filters.company} onChange={(event) => onChange('company', event.target.value)} placeholder="e.g. Acme" />
        </label>
        <label className="field field-with-icon">
          <span>Location</span>
          <div><MapPin size={16} /><input value={filters.location} onChange={(event) => onChange('location', event.target.value)} placeholder="e.g. Remote" /></div>
        </label>
        <div className="filter-actions">
          <button className="button button-primary" type="submit" disabled={loading}><Search size={17} /> {loading ? 'Searching' : 'Search jobs'}</button>
          <button className="button button-quiet" type="button" onClick={onClear}><RotateCcw size={16} /> Clear</button>
        </div>
      </div>
      <div className="filter-grid">
        <label className="field"><span>Source</span><select value={filters.source} onChange={(e) => onChange('source', e.target.value)}>
          <option value="">All sources</option><option value="python.org">Python.org</option><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option>
        </select></label>
        <label className="field"><span>Employment type</span><input value={filters.employment_type} onChange={(e) => onChange('employment_type', e.target.value)} placeholder="e.g. Full-time" /></label>
        <label className="field"><span>Workplace</span><select value={filters.workplace_type} onChange={(e) => onChange('workplace_type', e.target.value)}>
          <option value="">All workplaces</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="on-site">On-site</option>
        </select></label>
      </div>
      <p className="field-note">Filters search the server index. Missing source fields remain unavailable.</p>
    </form>
  )
}
