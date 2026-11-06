"""Sequential HTTP with finite timeouts, pacing, and bounded server-aware retries."""
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import requests


class SourceError(RuntimeError):
    pass


class HTTPClient:
    def __init__(self, session=None, sleep=time.sleep, monotonic=time.monotonic,
                 retries=3, pace=None, max_retry_after=120):
        self.session = session or requests.Session()
        self.sleep, self.monotonic = sleep, monotonic
        self.retries = retries
        self.pace = float(os.getenv('JOBPULSE_HTTP_PACE_SECONDS', '0.25')) if pace is None else pace
        if self.pace < 0 or not 0 <= retries <= 5:
            raise ValueError('Invalid pacing or retries')
        self.max_retry_after = max_retry_after
        self.last_request = None

    def get(self, url, *, params=None):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in {
            'www.python.org', 'boards-api.greenhouse.io', 'api.lever.co',
            'api.eu.lever.co', 'api.ashbyhq.com'
        } or parsed.username or parsed.password:
            raise SourceError('Unsupported source URL')
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                self.sleep(max(0, self.pace - (self.monotonic() - self.last_request)))
            self.last_request = self.monotonic()
            try:
                response = self.session.get(url, params=params, timeout=(10, 30),
                                            allow_redirects=False,
                                            headers={'User-Agent': 'JobPulse/1.0 (public job index)'})
            except (requests.Timeout, requests.ConnectionError) as error:
                if isinstance(error, requests.exceptions.ProxyError) and '403' in str(error):
                    raise SourceError('Proxy denied source access (HTTP 403)') from error
                if attempt == self.retries:
                    raise SourceError(type(error).__name__) from error
                self.sleep(2 ** attempt)
                continue
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == self.retries:
                    raise SourceError(f'HTTP {response.status_code}; retries exhausted')
                delay = float(2 ** attempt)
                retry = response.headers.get('Retry-After')
                if retry:
                    try:
                        delay = max(delay, float(retry))
                    except ValueError:
                        try:
                            delay = max(delay, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                if delay > self.max_retry_after:
                    raise SourceError('Retry-After exceeds retry budget; retry this source later')
                self.sleep(delay)
                continue
            if not 200 <= response.status_code < 300:
                raise SourceError(f'HTTP {response.status_code}')
            if len(response.content) > 20_000_000:
                raise SourceError('Source response exceeds size limit')
            return response
        raise SourceError('Request did not complete')

    def json(self, url, **kwargs):
        try:
            return self.get(url, **kwargs).json()
        except (ValueError, requests.exceptions.JSONDecodeError) as error:
            raise SourceError('Malformed source JSON') from error

    def html(self, url):
        text = self.get(url).text
        if not text.strip():
            raise SourceError('Empty source HTML')
        return text
