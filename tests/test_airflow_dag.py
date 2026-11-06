"""Run with optional Airflow dependencies installed; no scheduler DB or live AI required."""
import importlib
from unittest.mock import Mock, patch
import pytest


def module():
    pytest.importorskip('airflow')
    return importlib.import_module('jobpulse.dags.jobpulse_ingestion')


def test_real_dag_import_dependencies_and_bounded_ai(monkeypatch):
    m=module();dag=m.dag
    ids={f'ingest_{s}' for s in ['python_org','greenhouse','lever','ashby']}
    assert dag.get_task('start').downstream_task_ids==ids
    assert dag.get_task('validate_ingestion').upstream_task_ids==ids
    assert dag.get_task('validate_ingestion').trigger_rule=='all_done'
    assert dag.get_task('enrich_pending_jobs').upstream_task_ids=={'validate_ingestion'}
    assert dag.get_task('generate_pending_embeddings').upstream_task_ids=={'enrich_pending_jobs'}
    monkeypatch.setenv('JOBPULSE_ENABLE_AI','false')
    assert m.enrich_pending_jobs()=={'enabled':False}
    assert m.generate_pending_embeddings()=={'enabled':False}
    monkeypatch.setenv('JOBPULSE_AI_BATCH_SIZE','501')
    with pytest.raises(ValueError): m.batch_limit()


def test_validation_reports_failed_or_missing_source():
    m=module();ti=Mock()
    ti.xcom_pull.side_effect=[[{'status':'succeeded'}],None,[],[]]
    with pytest.raises(RuntimeError,match='greenhouse'):m.validate_ingestion(ti=ti)
    ti.xcom_pull.side_effect=[[{'status':'failed'}],[],[],[]]
    with pytest.raises(RuntimeError,match='python.org'):m.validate_ingestion(ti=ti)
    ti.xcom_pull.side_effect=[[{'status':'succeeded'}],[],[],[]]
    assert m.validate_ingestion(ti=ti)==[{'status':'succeeded'}]


def test_failed_source_task_pushes_status_and_raises():
    m=module();ti=Mock()
    with patch.object(m,'run_sources',return_value=[{'status':'failed'}]):
        with pytest.raises(RuntimeError):m.ingest_source('lever',ti=ti)
    ti.xcom_push.assert_called_once_with(key='source_results',value=[{'status':'failed'}])
