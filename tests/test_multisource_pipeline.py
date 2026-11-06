from unittest.mock import Mock, patch
from jobpulse.ingestion.pipeline import run_sources
from jobpulse.ingestion.sources import Board


def test_failed_source_does_not_prevent_other_boards():
    boards=[Board('lever','a'),Board('lever','b'),Board('ashby','a')]
    broken=Mock();broken.fetch.side_effect=ValueError('malformed JSON')
    good=Mock();good.fetch.return_value=[]
    with patch('jobpulse.ingestion.pipeline.begin_run',side_effect=['1','2','3']), \
         patch('jobpulse.ingestion.pipeline.fail_run') as fail, \
         patch('jobpulse.ingestion.pipeline.adapter_for',side_effect=[broken,good,good]), \
         patch('jobpulse.ingestion.pipeline.persist_snapshot',return_value={'inserted':0}) as persist:
        results=run_sources(boards)
    assert [r['status'] for r in results]==['failed','succeeded','succeeded']
    assert results[0]['stale']==0
    assert persist.call_count==2 and fail.call_count==1
