import uuid
from typing import TYPE_CHECKING, Union

import structlog
from aijson.utils.async_utils import Timer
from aijson.utils.misc_utils import recursive_defaultdict

DocumentId = str
Value = dict

if TYPE_CHECKING:
    from google.cloud.firestore_v1 import (
        AsyncDocumentReference,
        AsyncClient as FirestoreAsyncClient,
    )


class DocumentRepo:
    @staticmethod
    def _get_collection_key(collection: str | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(collection, str):
            return tuple(collection.split("/"))
        return collection

    async def store(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: str | tuple[str, ...],
        value: Value,
        document_id: DocumentId | None = None,
    ) -> DocumentId:
        timer = Timer()
        timer.start()
        final_document_id = await self._store(
            log=log,
            collection=self._get_collection_key(collection),
            value=value,
            document_id=document_id,
        )
        timer.end()
        log.info(
            "Saved document",
            collection=collection,
            document_id=final_document_id,
            duration=timer.wall_time,
        )
        return final_document_id

    async def _store(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        value: Value,
        document_id: DocumentId | None,
    ) -> DocumentId:
        raise NotImplementedError

    async def exists(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: str | tuple[str, ...],
        document_id: DocumentId,
    ) -> bool:
        timer = Timer()
        timer.start()
        exists = await self._exists(
            log=log,
            collection=self._get_collection_key(collection),
            document_id=document_id,
        )
        timer.end()
        log.info(
            "Checked blob existence",
            collection=collection,
            document_id=document_id,
            duration=timer.wall_time,
        )
        return exists

    async def _exists(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        document_id: DocumentId,
    ) -> bool:
        raise NotImplementedError

    async def retrieve(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: str | tuple[str, ...],
        document_id: DocumentId,
    ) -> Value:
        timer = Timer()
        timer.start()
        value = await self._retrieve(
            log=log,
            collection=self._get_collection_key(collection),
            document_id=document_id,
        )
        timer.end()
        log.info(
            "Retrieved document",
            collection=collection,
            document_id=document_id,
            duration=timer.wall_time,
        )
        return value

    async def _retrieve(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        document_id: DocumentId,
    ) -> Value:
        raise NotImplementedError

    async def retrieve_all(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: str | tuple[str, ...],
    ) -> dict[DocumentId, Value]:
        timer = Timer()
        timer.start()
        value = await self._retrieve_all(
            log=log,
            collection=self._get_collection_key(collection),
        )
        timer.end()
        log.info(
            "Retrieved all documents",
            collection=collection,
            duration=timer.wall_time,
        )
        return value

    async def _retrieve_all(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
    ) -> dict[DocumentId, Value]:
        raise NotImplementedError


class InMemoryDocumentRepo(DocumentRepo):
    def __init__(self):
        self.collections = recursive_defaultdict()

    def _get_collection(self, collection: tuple[str, ...]) -> dict[DocumentId, Value]:
        coll = self.collections
        for key in collection:
            coll = coll[key]
        return coll

    async def _store(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        value: Value,
        document_id: DocumentId | None,
    ) -> DocumentId:
        if document_id is None:
            document_id = str(uuid.uuid4())
        coll = self._get_collection(collection)

        # wrap value in defaultdict
        defaultdict_value = recursive_defaultdict() | value

        coll[document_id] = defaultdict_value
        return document_id

    async def _exists(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        document_id: DocumentId,
    ) -> bool:
        coll = self._get_collection(collection)
        return document_id in coll

    async def _retrieve(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        document_id: DocumentId,
    ) -> Value:
        coll = self._get_collection(collection)
        return coll[document_id]

    async def _retrieve_all(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
    ) -> dict[DocumentId, Value]:
        coll = self._get_collection(collection)
        return coll


class FirestoreDocumentRepo(DocumentRepo):
    def __init__(self, db: "FirestoreAsyncClient"):
        self.db = db

    def _get_doc_ref(
        self, collection: tuple[str, ...], document_id: Union[str, None]
    ) -> "AsyncDocumentReference":
        path = "/".join(
            collection
        )  # the mocking library only supports this format, should be the same
        coll = self.db.collection(path)
        doc_ref = coll.document(document_id)  # pyright: ignore [reportArgumentType]
        return doc_ref

    async def _store(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        value: Value,
        document_id: DocumentId | None,
    ) -> DocumentId:
        doc_ref = self._get_doc_ref(collection, document_id)
        await doc_ref.set(value)
        return doc_ref.id

    async def _exists(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        document_id: DocumentId,
    ) -> bool:
        doc_ref = self._get_doc_ref(collection, document_id)
        doc = await doc_ref.get()
        return doc.exists

    async def _retrieve(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
        document_id: DocumentId,
    ) -> Value:
        doc_ref = self._get_doc_ref(collection, document_id)
        doc = await doc_ref.get()
        if not doc.exists:
            raise FileNotFoundError("Document does not exist")
        val = doc.to_dict()
        if val is None:
            raise FileNotFoundError("Document is empty")
        return val

    async def _retrieve_all(
        self,
        log: structlog.stdlib.BoundLogger,
        collection: tuple[str, ...],
    ) -> dict[DocumentId, Value]:
        coll = self.db.collection("/".join(collection))
        docs = {}
        # TODO why does pyright not like this?
        async for docref in coll.stream():  # pyright: ignore
            docs[docref.id] = docref.to_dict()
        return docs
