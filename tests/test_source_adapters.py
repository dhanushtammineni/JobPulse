from unittest.mock import Mock
import pytest
import requests
from jobpulse.ingestion.sources import Board, Greenhouse, Lever, Ashby, configured_boards
from jobpulse.ingestion.http import HTTPClient, SourceError


def client(payload):
    http = Mock()
    http.json.return_value = payload
    return http


def test_greenhouse_optional_fields_and_actual_url():
    http = client({'jobs': [{'id': 42, 'title': 'Engineer', 'absolute_url': 'https://example.org/jobs/42',
                            'content': '<p>Build APIs</p>', 'updated_at': '2026-01-01'}], 'meta': {'total': 1}})
    job, = Greenhouse(http).fetch(Board('greenhouse', 'acme'))
    assert job.company is None and job.location is None and job.posted_date is None
    assert job.source_job_id == '42' and job.description == 'Build APIs'
    assert job.url == 'https://example.org/jobs/42'
    assert http.json.call_args.kwargs['params'] == {'content': 'true'}


def test_lever_pagination_eu_and_full_description():
    http = Mock()
    http.json.side_effect = [[{'id': 'a', 'text': 'Engineer', 'hostedUrl': 'https://jobs.lever.co/acme/a',
                              'applyUrl': 'https://jobs.lever.co/acme/a/apply',
                              'categories': {'location': 'Berlin', 'commitment': 'Full-time'},
                              'descriptionPlain': 'Build APIs', 'lists': [{'text': 'Skills', 'content': '<li>Python</li>'}],
                              'workplaceType': 'hybrid', 'salaryRange': {'min': 10, 'max': 20, 'currency': 'EUR'}}], []]
    job, = Lever(http, page_size=1).fetch(Board('lever', 'acme', 'Acme', 'eu'))
    assert 'Python' in job.description and job.workplace_type == 'hybrid'
    assert job.salary_currency == 'EUR' and job.apply_url.endswith('/apply')
    assert http.json.call_args.kwargs['params']['skip'] == 1
    assert http.json.call_args.args[0].startswith('https://api.eu.lever.co/')


def test_lever_incomplete_page_and_repeated_ids_fail():
    http = client([{'id': 'a', 'text': 'Engineer', 'hostedUrl': 'https://example.org/a'}])
    with pytest.raises(SourceError, match='repeated'):
        Lever(http, page_size=1).fetch(Board('lever', 'acme'))
    with pytest.raises(SourceError, match='incomplete'):
        Lever(http, page_size=1, max_pages=1).fetch(Board('lever', 'acme'))


def test_ashby_only_listed_compensation_remote_and_date():
    comp = {'compensationTierSummary': [{'currency': 'USD', 'minValue': 100, 'maxValue': 200}]}
    http = client({'jobs': [{'id': 'a', 'title': 'Engineer', 'isListed': True,
                            'jobUrl': 'https://jobs.ashbyhq.com/acme/a', 'isRemote': True,
                            'compensation': comp, 'publishedAt': '2026-01-01T12:00:00Z'},
                           {'id': 'b', 'isListed': False}]})
    job, = Ashby(http).fetch(Board('ashby', 'acme'))
    assert job.salary_currency == 'USD' and 'minValue' in job.salary
    assert job.workplace_type == 'remote' and str(job.posted_date) == '2026-01-01'
    assert job.company is None and job.employment_type is None


@pytest.mark.parametrize('adapter,payload', [(Greenhouse, {}), (Lever, {}), (Ashby, {'jobs': None}),
    (Greenhouse, {'jobs': [{'id': 1, 'title': 'x', 'absolute_url': 'javascript:alert(1)'}]}),
    (Greenhouse, {'jobs': [], 'meta': {'total': 1}})])
def test_malformed_responses_fail_closed(adapter, payload):
    with pytest.raises((SourceError, ValueError)):
        adapter(client(payload)).fetch(Board('greenhouse', 'acme'))


def response(status=200, retry=None):
    r = Mock(status_code=status, content=b'{}', headers={'Retry-After': retry} if retry else {})
    r.json.return_value = {}
    return r


def test_http_429_retry_after_server_error_and_timeouts():
    session, sleep = Mock(), Mock()
    session.get.side_effect = [requests.Timeout(), response(429, '5'), response(503), response()]
    http = HTTPClient(session, sleep=sleep, pace=0)
    assert http.json('https://api.lever.co/v0/postings/acme') == {}
    assert session.get.call_count == 4
    assert any(call.args == (5.0,) for call in sleep.call_args_list)
    assert session.get.call_args.kwargs['timeout'] == (10, 30)
    assert session.get.call_args.kwargs['allow_redirects'] is False


def test_http_fails_after_budget_and_does_not_retry_early():
    session, sleep = Mock(), Mock()
    session.get.return_value = response(429, '500')
    with pytest.raises(SourceError, match='budget'):
        HTTPClient(session, sleep=sleep).json('https://api.ashbyhq.com/posting-api/job-board/acme')
    sleep.assert_not_called()
    session.get.return_value = response(503)
    with pytest.raises(SourceError, match='exhausted'):
        HTTPClient(session, sleep=sleep, pace=0).json('https://api.lever.co/v0/postings/acme')
    assert session.get.call_count == 5


def test_malformed_json():
    session = Mock()
    session.get.return_value = response()
    session.get.return_value.json.side_effect = ValueError('invalid')
    with pytest.raises(SourceError, match='Malformed'):
        HTTPClient(session).json('https://api.lever.co/v0/postings/acme')


def test_configuration_requires_explicit_boards(monkeypatch):
    monkeypatch.setenv('JOBPULSE_SOURCES', 'lever')
    with pytest.raises(ValueError, match='at least one'): configured_boards()
    monkeypatch.setenv('JOBPULSE_LEVER_BOARDS', '[{"board":"acme","company":"Acme","region":"eu"}]')
    assert configured_boards() == [Board('lever', 'acme', 'Acme', 'eu')]
    monkeypatch.setenv('JOBPULSE_LEVER_BOARDS', '[{"board":"../bad"}]')
    with pytest.raises(ValueError): configured_boards()
