from unittest.mock import patch
from fastapi.testclient import TestClient
import api


def test_source_filters_pagination_and_empty_result():
    result={'items':[],'total':0,'page':2,'page_size':5,'ingestion':[]}
    with patch('api.list_jobs',return_value=result) as listings:
        response=TestClient(api.app).get('/jobs',params=dict(source='lever',keyword='Python',company='Acme',
            location='Berlin',employment_type='Full-time',workplace_type='hybrid',page=2,page_size=5))
    assert response.status_code==200 and response.json()==result
    assert listings.call_args.kwargs==dict(source='lever',keyword='Python',company='Acme',location='Berlin',
        employment_type='Full-time',workplace_type='hybrid',page=2,page_size=5)


def test_invalid_filters_and_pagination_rejected():
    for query in ['page=0','page_size=101','source=unknown','workplace_type=unknown']:
        assert TestClient(api.app).get('/jobs?'+query).status_code==422


def test_database_failure_hidden():
    with patch('api.list_jobs',side_effect=api.psycopg2.OperationalError('private details')):
        response=TestClient(api.app).get('/jobs')
    assert response.status_code==503 and 'private' not in response.text
