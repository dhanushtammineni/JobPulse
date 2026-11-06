"""Airflow 2.11 DAG; all network/DB/provider work happens inside task callables."""
import logging
import os
from datetime import datetime, timedelta
from functools import partial
from airflow import DAG
from airflow.operators.python import PythonOperator
from jobpulse.ingestion.pipeline import run_sources

logger = logging.getLogger(__name__)
SOURCES = ('python.org','greenhouse','lever','ashby')
TASK_IDS = {source:'ingest_'+source.replace('.','_') for source in SOURCES}


def ingest_source(source, **context):
    results = run_sources(source=source)
    context['ti'].xcom_push(key='source_results', value=results)
    if any(result['status'] != 'succeeded' for result in results):
        raise RuntimeError(f'{source} ingestion failed; see source run statuses')
    return results


def validate_ingestion(**context):
    results = []
    for source, task_id in TASK_IDS.items():
        value = context['ti'].xcom_pull(task_ids=task_id,key='source_results')
        if value is None or any(item['status'] != 'succeeded' for item in value):
            raise RuntimeError(f'{source} did not complete successfully')
        results.extend(value)
    if not results: raise RuntimeError('No configured sources were ingested')
    logger.info('Validated %s successful board runs',len(results))
    return results


def batch_limit():
    value=int(os.getenv('JOBPULSE_AI_BATCH_SIZE','25'))
    if not 1 <= value <= 500: raise ValueError('JOBPULSE_AI_BATCH_SIZE must be 1..500')
    return value


def enrich_pending_jobs():
    if os.getenv('JOBPULSE_ENABLE_AI','false').lower() != 'true': return {'enabled':False}
    from jobpulse.ai.batch_enrichment import enrich_jobs_batch
    stats = enrich_jobs_batch(batch_limit()).as_dict()
    if stats['failed']: raise RuntimeError('Some AI enrichment jobs failed')
    return stats


def generate_pending_embeddings():
    if os.getenv('JOBPULSE_ENABLE_AI','false').lower() != 'true': return {'enabled':False}
    from jobpulse.ai.batch_embeddings import embed_jobs_batch
    stats = embed_jobs_batch(batch_limit()).as_dict()
    if stats['failed']: raise RuntimeError('Some embeddings failed')
    return stats


with DAG(dag_id='jobpulse_ingestion', start_date=datetime(2026,1,1),
         schedule=os.getenv('JOBPULSE_AIRFLOW_SCHEDULE','0 * * * *'),catchup=False,
         max_active_runs=1, default_args={
             'owner':'jobpulse','retries':int(os.getenv('JOBPULSE_AIRFLOW_RETRIES','2')),
             'retry_delay':timedelta(minutes=int(os.getenv('JOBPULSE_AIRFLOW_RETRY_DELAY_MINUTES','5')))},
         tags=['jobpulse','ingestion']) as dag:
    start=PythonOperator(task_id='start',python_callable=lambda: logger.info('Starting ingestion'))
    ingestion=[PythonOperator(task_id=TASK_IDS[source],python_callable=partial(ingest_source,source)) for source in SOURCES]
    validate=PythonOperator(task_id='validate_ingestion',python_callable=validate_ingestion,trigger_rule='all_done')
    enrich=PythonOperator(task_id='enrich_pending_jobs',python_callable=enrich_pending_jobs)
    embed=PythonOperator(task_id='generate_pending_embeddings',python_callable=generate_pending_embeddings)
    finish=PythonOperator(task_id='finish',python_callable=lambda: logger.info('Ingestion and enabled AI batches completed'))
    start >> ingestion >> validate >> enrich >> embed >> finish
