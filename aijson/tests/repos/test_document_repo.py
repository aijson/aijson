import pytest


@pytest.fixture
def document_collection():
    return "test_collection"


@pytest.fixture
def document_value():
    return {
        "foo": "bar",
        "bar": 2,
    }


@pytest.fixture
def document_value_2():
    return {
        "bar": "foo",
        "foo": 3,
    }


async def test_store_and_retrieve(
    log, document_repo, document_collection, document_value
):
    document_id = await document_repo.store(log, document_collection, document_value)
    retrieved_value = await document_repo.retrieve(
        log, document_collection, document_id
    )
    assert document_value == retrieved_value


async def test_store_and_retrieve_two(
    log, document_repo, document_collection, document_value, document_value_2
):
    document_id = await document_repo.store(log, document_collection, document_value)
    document_id_2 = await document_repo.store(
        log, document_collection, document_value_2
    )
    retrieved_value = await document_repo.retrieve(
        log, document_collection, document_id
    )
    retrieved_value_2 = await document_repo.retrieve(
        log, document_collection, document_id_2
    )
    assert document_value == retrieved_value
    assert document_value_2 == retrieved_value_2


async def test_exists(log, document_repo, document_collection, document_value):
    document_id = await document_repo.store(log, document_collection, document_value)
    assert await document_repo.exists(log, document_collection, document_id) is True
