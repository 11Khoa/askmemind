from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import Mock
import os,uuid
import pytest
from redis import Redis
from fastapi import HTTPException
from app.services.token_store import TokenStore
from app.core.concurrency import slot
from app.core.data_scope import DataScope


def test_exception_and_normal_completion_release_the_lease():
    store=Mock();store.acquire_slots.return_value=True
    with pytest.raises(ValueError):
        with contextmanager(slot)(store,'test',uuid.uuid4(),DataScope(uuid.uuid4()),4,2,10):
            raise ValueError('provider failed')
    store.release_slots.assert_called_once()


def test_rejection_is_429_and_does_not_release_another_requests_lease():
    store=Mock();store.acquire_slots.return_value=False
    with pytest.raises(HTTPException) as error:
        with contextmanager(slot)(store,'test',uuid.uuid4(),DataScope(uuid.uuid4()),1,1,10):pass
    assert error.value.status_code==429
    store.release_slots.assert_not_called()


@pytest.mark.skipif(not os.getenv('AUTH_TEST_REDIS_URL'),reason='Requires test Redis')
def test_real_redis_admission_is_atomic_and_reclaims_expired_slots():
    client=Redis.from_url(os.environ['AUTH_TEST_REDIS_URL'])
    store=TokenStore(client);prefix=f'test:slots:{uuid.uuid4()}'
    keys=[prefix+':global',prefix+':user']
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            admitted=list(pool.map(lambda token:store.acquire_slots(keys,[1,1],token,30),['a','b']))
        assert sum(admitted)==1
        token='a' if admitted[0] else 'b'
        store.release_slots(keys,token)
        assert store.acquire_slots(keys,[1,1],'next',30)
        for key in keys:client.zadd(key,{'next':0})
        assert store.acquire_slots(keys,[1,1],'after-expiry',30)
    finally:
        client.delete(*keys);client.close()
