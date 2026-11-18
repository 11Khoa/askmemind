from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid
from app.services.rag_service import RagService


def test_agent_summary_never_logs_rewritten_question():
    marker='SyntheticPrivateMarker42'
    agent=Mock()
    agent.retrieve.return_value=SimpleNamespace(chunks=[],state=SimpleNamespace(
        retry_count=1,rewritten_query=marker,retrieval_score=0.0,decisions=['rewrite']))
    service=RagService(Mock(active_method='fts'),Mock(),Mock(),retrieval_agent=agent,agentic_retrieval_enabled=True)
    with patch('app.services.rag_service.log_event') as log:
        service.answer_question(marker,uuid.uuid4())
    assert marker not in str(log.call_args_list)
    summary=next(c for c in log.call_args_list if c.args[2]=='rag.agent.completed')
    assert summary.kwargs['query_rewritten'] is True
    assert 'rewritten_query' not in summary.kwargs
