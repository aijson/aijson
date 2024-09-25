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


async def test_add_to_field(log, document_repo):
    org_id = await document_repo.store(
        log,
        "orgs",
        {
            "name": "someorg",
        },
    )
    user_id = await document_repo.store(
        log,
        f"orgs/{org_id}/users",
        {
            "name": "someuser",
        },
    )

    # print(await document_repo.retrieve(log, "test", id_))
    # print(await document_repo.retrieve(log, "test/foo", id2))
    assert await document_repo.retrieve(log, "orgs", org_id) == {
        "name": "someorg",
        "users": {
            user_id: {
                "name": "someuser",
            }
        },
    }
    assert await document_repo.retrieve(log, f"orgs/{org_id}/users", user_id) == {
        "name": "someuser",
    }


async def test_defined_document_id(log, document_repo):
    document_id = "some_id"
    await document_repo.store(log, "test", {"foo": "bar"}, document_id)
    assert await document_repo.retrieve(log, "test", document_id) == {"foo": "bar"}


async def test_retrieve_all(log, document_repo):
    expected = [{"foo": f"bar{i}"} for i in range(4)]
    for value in expected:
        await document_repo.store(log, "test", value)
    results = await document_repo.retrieve_all(log, "test")
    assert len(results) == 4
    for exp in expected:
        assert exp in results.values()
