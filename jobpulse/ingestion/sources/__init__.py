"""Public board adapters. No authenticated recruiting/management APIs are used."""
from dataclasses import dataclass
from datetime import datetime
import json
from html import unescape
import os
import re
from typing import Protocol
from bs4 import BeautifulSoup
from jobpulse.ingestion.models import Job, valid_url
from jobpulse.ingestion.http import HTTPClient, SourceError


@dataclass(frozen=True)
class Board:
    source: str
    board: str = ''
    company: str | None = None
    region: str = 'global'


class SourceAdapter(Protocol):
    def fetch(self, board: Board) -> list[Job]: ...


def text(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise SourceError('Expected source text')
    return BeautifulSoup(unescape(value), 'lxml').get_text(' ', strip=True) or None


def timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceError('Invalid source timestamp')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError as error:
        raise SourceError('Invalid source timestamp') from error


def listing(board, record, *, title, url, location=None, description=None, **kwargs):
    if not isinstance(record, dict) or not record.get('id') or not title:
        raise SourceError('Missing listing identity or title')
    if not isinstance(record['id'], (str, int)) or isinstance(record['id'], bool):
        raise SourceError('Invalid listing identity')
    valid_url(url)
    if kwargs.get('apply_url'):
        valid_url(kwargs['apply_url'])
    return Job(text(title), board.company, text(location), kwargs.pop('posted_date', None), url,
               source=board.source, source_job_id=str(record['id']), source_board=board.board,
               description=text(description), **kwargs)


class Greenhouse:
    def __init__(self, http): self.http = http

    def fetch(self, board):
        data = self.http.json(f'https://boards-api.greenhouse.io/v1/boards/{board.board}/jobs',
                              params={'content': 'true'})
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            raise SourceError('Invalid Greenhouse jobs response')
        meta = data.get('meta') or {}
        if 'total' in meta and meta['total'] != len(data['jobs']):
            raise SourceError('Incomplete Greenhouse response')
        jobs = []
        for item in data['jobs']:
            if not isinstance(item, dict): raise SourceError('Invalid Greenhouse listing')
            location = item.get('location') or {}
            jobs.append(listing(board, item, title=item.get('title'), url=item.get('absolute_url'),
                                location=location.get('name'), description=item.get('content')))
        # updated_at is an edit timestamp, not a posting date.
        return jobs


class Lever:
    def __init__(self, http, page_size=100, max_pages=100):
        self.http, self.page_size, self.max_pages = http, page_size, max_pages

    def fetch(self, board):
        host = 'api.eu.lever.co' if board.region == 'eu' else 'api.lever.co'
        jobs, seen = [], set()
        for page in range(self.max_pages):
            data = self.http.json(f'https://{host}/v0/postings/{board.board}',
                                  params={'mode': 'json', 'skip': page * self.page_size, 'limit': self.page_size})
            if not isinstance(data, list) or len(data) > self.page_size:
                raise SourceError('Invalid Lever page')
            for item in data:
                if not isinstance(item, dict) or not item.get('id') or item['id'] in seen:
                    raise SourceError('Invalid or repeated Lever posting; pagination incomplete')
                seen.add(item['id'])
                categories = item.get('categories') or {}
                parts = [item.get('descriptionPlain') or item.get('description')]
                for section in item.get('lists') or []:
                    parts.extend([section.get('text'), section.get('content')])
                parts.append(item.get('additionalPlain') or item.get('additional'))
                salary = item.get('salaryRange') or {}
                jobs.append(listing(board, item, title=item.get('text'), url=item.get('hostedUrl'),
                                    apply_url=item.get('applyUrl'), location=categories.get('location'),
                                    description='\n'.join(filter(None, parts)) or None,
                                    employment_type=text(categories.get('commitment')),
                                    workplace_type=workplace(item.get('workplaceType')),
                                    salary=json.dumps(salary, sort_keys=True) if salary else text(item.get('salaryDescriptionPlain')),
                                    salary_currency=salary.get('currency'), source_metadata={'categories': categories, 'country': item.get('country')}))
            if len(data) < self.page_size:
                return jobs
        raise SourceError('Lever pagination limit reached; run is incomplete')


def workplace(value):
    if value is None: return None
    normalized = str(value).lower().replace('_', '-').replace('onsite', 'on-site')
    return normalized if normalized in {'remote', 'hybrid', 'on-site'} else None


def compensation_currencies(value):
    """Currency can be attached to individual compensation components, not the summary."""
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'currency', 'currencyCode'} and isinstance(item, str): result.add(item)
            elif isinstance(item, (dict,list)): result.update(compensation_currencies(item))
    elif isinstance(value, list):
        for item in value: result.update(compensation_currencies(item))
    return result


class Ashby:
    def __init__(self, http): self.http = http

    def fetch(self, board):
        data = self.http.json(f'https://api.ashbyhq.com/posting-api/job-board/{board.board}',
                              params={'includeCompensation': 'true'})
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            raise SourceError('Invalid Ashby jobs response')
        jobs = []
        for item in data['jobs']:
            if not isinstance(item, dict): raise SourceError('Invalid Ashby listing')
            if item.get('isListed') is not True: continue
            compensation = item.get('compensation')
            if compensation is not None and not isinstance(compensation, dict):
                raise SourceError('Invalid Ashby compensation')
            currencies = compensation_currencies(compensation)
            jobs.append(listing(board, item, title=item.get('title'), url=item.get('jobUrl'),
                                apply_url=item.get('applyUrl'), location=item.get('location'),
                                description=item.get('descriptionPlain') or item.get('descriptionHtml'),
                                employment_type=text(item.get('employmentType')),
                                workplace_type=workplace(item.get('workplaceType')) or ('remote' if item.get('isRemote') is True else None),
                                salary=json.dumps(compensation, sort_keys=True) if compensation else None,
                                salary_currency=next(iter(currencies)) if len(currencies) == 1 else None,
                                posted_date=timestamp(item.get('publishedAt')),
                                source_metadata={key: item[key] for key in ('department','team','isRemote','secondaryLocations') if key in item}))
        return jobs


class PythonOrg:
    def __init__(self, http): self.http = http

    def fetch(self, board):
        from jobpulse.ingestion.parser import parse_html, extract_jobs
        soup = parse_html(self.http.html('https://www.python.org/jobs/'))
        if soup.find('ol', class_='list-recent-jobs') is None:
            raise SourceError('Python.org listing container missing')
        jobs = extract_jobs(soup, detail_fetcher=self.http.html)
        if not jobs: raise SourceError('Python.org returned no job listings')
        for job in jobs:
            valid_url(job.url)
            job.source_job_id = job.source_job_id or job.url
        return jobs


def configured_boards():
    """Explicit configuration; board slugs never become invented company names."""
    enabled = [v.strip() for v in os.getenv('JOBPULSE_SOURCES', 'python.org').split(',') if v.strip()]
    if len(enabled) != len(set(enabled)) or set(enabled) - {'python.org', 'greenhouse', 'lever', 'ashby'}:
        raise ValueError('Unknown or repeated JOBPULSE_SOURCES')
    result = []
    for source in enabled:
        if source == 'python.org':
            result.append(Board(source)); continue
        raw = json.loads(os.getenv('JOBPULSE_' + source.upper() + '_BOARDS', '[]'))
        if not isinstance(raw, list) or not raw:
            raise ValueError(f'Configure at least one {source} board')
        for item in raw:
            if not isinstance(item, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', item.get('board', '')):
                raise ValueError('Invalid board identifier')
            if item.get('region', 'global') not in {'global', 'eu'}:
                raise ValueError('Unsupported region')
            if source != 'lever' and item.get('region', 'global') != 'global':
                raise ValueError('Only Lever supports a regional endpoint')
            result.append(Board(source, item['board'], text(item.get('company')), item.get('region', 'global')))
    keys = [(b.source, b.board) for b in result]
    if len(keys) != len(set(keys)): raise ValueError('Repeated board configuration')
    return result


def adapter_for(source, http=None):
    return {'python.org': PythonOrg, 'greenhouse': Greenhouse, 'lever': Lever, 'ashby': Ashby}[source](http or HTTPClient())
