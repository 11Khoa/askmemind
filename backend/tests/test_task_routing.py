import pytest
from app.core.celery_app import celery_app


@pytest.mark.parametrize('task,queue',[
    ('documents.process','documents'),('documents.dispatch','maintenance'),
    ('demo.cleanup','maintenance'),('auth.send_password_reset','maintenance'),
])
def test_control_tasks_do_not_wait_behind_ocr(task,queue):
    route=celery_app.amqp.router.route({},task,args=(),kwargs={})
    assert route['queue'].name==queue


def test_visibility_timeout_exceeds_hard_worker_deadline():
    deadline=celery_app.conf.task_annotations['documents.process']['time_limit']
    assert celery_app.conf.broker_transport_options['visibility_timeout']>deadline
