"""Provider-neutral job model; the legacy URL and positional constructor remain supported."""
from datetime import date, datetime
from hashlib import sha256
import json
from urllib.parse import urlsplit

CONTENT_FIELDS = ('title', 'company', 'location', 'description', 'employment_type',
                  'salary', 'salary_currency', 'workplace_type', 'posted_date')
SEMANTIC_FIELDS = ('title', 'company', 'location', 'description', 'employment_type',
                   'salary', 'salary_currency', 'workplace_type')


def valid_url(value):
    if not isinstance(value, str):
        raise ValueError('Listing URL must be a string')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Listing URLs must be absolute HTTPS URLs without credentials')
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Invalid whitespace in URL')
    return value


def content_hash(values):
    return sha256(json.dumps({k: values.get(k) for k in CONTENT_FIELDS},
                             sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


class Job:
    def __init__(self, title, company, location, posted_date, url, source='python.org',
                 first_seen_at=None, last_seen_at=None, is_active=True, source_job_id=None,
                 description=None, employment_type=None, salary=None, *, id=None,
                 source_board='', apply_url=None, salary_currency=None, workplace_type=None,
                 content_hash=None, **extra):
        self.title, self.company, self.location = title, company, location
        self.posted_date, self.url, self.source = posted_date, url, source
        self.first_seen_at, self.last_seen_at, self.is_active = first_seen_at, last_seen_at, is_active
        self.source_job_id, self.description = source_job_id, description
        self.employment_type, self.salary = employment_type, salary
        self.id, self.source_board, self.apply_url = id, source_board, apply_url
        self.salary_currency, self.workplace_type = salary_currency, workplace_type
        self.content_hash = content_hash

    @property
    def job_url(self):
        return self.url

    def to_dict(self):
        def serial(value):
            return value.isoformat() if isinstance(value, (date, datetime)) else value
        fields = ('id', 'title', 'company', 'location', 'posted_date', 'url', 'source',
                  'source_board', 'source_job_id', 'description', 'employment_type', 'salary',
                  'salary_currency', 'workplace_type', 'apply_url', 'first_seen_at',
                  'last_seen_at', 'is_active', 'content_hash')
        result = {key: serial(getattr(self, key)) for key in fields}
        result['job_url'] = self.url
        return result

    @classmethod
    def from_row(cls, row):
        return cls(*row)
