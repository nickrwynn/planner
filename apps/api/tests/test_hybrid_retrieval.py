from __future__ import annotations

from sqlalchemy import select

from app.ai.retrieval import retrieve_chunks
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.models.user import User
from app.search.hybrid import select_chunks_hybrid


class _FakeEmb:
    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 1.0, 0.0] for _ in texts]


def test_retrieve_chunks_hybrid_keyword_fills_when_no_embeddings(monkeypatch, db_session):
    monkeypatch.setattr("app.ai.retrieval.get_embeddings_provider", lambda: _FakeEmb())

    user = User(email="hyb@test.dev", name="Hyb")
    db_session.add(user)
    db_session.commit()

    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Doc",
        resource_type="file",
        storage_path=None,
        parse_status="parsed",
        ocr_status="skipped",
        index_status="done",
        lifecycle_state="searchable",
    )
    db_session.add(res)
    db_session.commit()

    db_session.add(
        ResourceChunk(
            user_id=user.id,
            resource_id=res.id,
            chunk_index=0,
            page_number=None,
            text="keyword_only_chunk_xyz",
            embedding=None,
        )
    )
    db_session.commit()

    out = retrieve_chunks(db_session, user_id=user.id, query="keyword_only_chunk_xyz", k=4)
    assert len(out) >= 1
    assert any("keyword_only_chunk_xyz" in x.text for x in out)


def test_select_chunks_hybrid_merges_semantic_and_keyword(db_session):
    user = User(email="hyb2@test.dev", name="Hyb2")
    db_session.add(user)
    db_session.commit()

    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Doc2",
        resource_type="file",
        storage_path=None,
        parse_status="parsed",
        ocr_status="skipped",
        index_status="done",
        lifecycle_state="searchable",
    )
    db_session.add(res)
    db_session.commit()

    db_session.add(
        ResourceChunk(
            user_id=user.id,
            resource_id=res.id,
            chunk_index=0,
            page_number=None,
            text="fill_by_keyword_only",
            embedding=None,
        )
    )
    db_session.add(
        ResourceChunk(
            user_id=user.id,
            resource_id=res.id,
            chunk_index=1,
            page_number=None,
            text="other",
            embedding=[1.0, 0.0],
        )
    )
    db_session.commit()

    stmt = select(ResourceChunk).where(ResourceChunk.resource_id == res.id)
    fake = _FakeEmb()
    ranked = select_chunks_hybrid(db_session, stmt, "fill_by_keyword_only", fake, 4, candidate_limit=50)
    texts = [c.text for c, _ in ranked]
    assert any("fill_by_keyword_only" in t for t in texts)
    semantic_hits = [(c, s) for c, s in ranked if c.text == "other" and s is not None]
    assert len(semantic_hits) >= 1


def test_select_chunks_hybrid_is_deterministic_for_equal_candidates(db_session):
    user = User(email="hyb3@test.dev", name="Hyb3")
    db_session.add(user)
    db_session.commit()

    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Doc3",
        resource_type="file",
        storage_path=None,
        parse_status="parsed",
        ocr_status="skipped",
        index_status="done",
        lifecycle_state="searchable",
    )
    db_session.add(res)
    db_session.commit()

    db_session.add_all(
        [
            ResourceChunk(
                user_id=user.id,
                resource_id=res.id,
                chunk_index=0,
                page_number=None,
                text="stable token",
                embedding=None,
            ),
            ResourceChunk(
                user_id=user.id,
                resource_id=res.id,
                chunk_index=1,
                page_number=None,
                text="stable token",
                embedding=None,
            ),
        ]
    )
    db_session.commit()

    stmt = select(ResourceChunk).where(ResourceChunk.user_id == user.id)
    first = [c.id for c, _ in select_chunks_hybrid(db_session, stmt, "stable token", None, 10, candidate_limit=50)]
    second = [c.id for c, _ in select_chunks_hybrid(db_session, stmt, "stable token", None, 10, candidate_limit=50)]
    assert first == second


def test_retrieval_prefers_exact_keyword_chunk(db_session):
    user = User(email="hyb4@test.dev", name="Hyb4")
    db_session.add(user)
    db_session.commit()

    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Doc4",
        resource_type="file",
        storage_path=None,
        parse_status="parsed",
        ocr_status="skipped",
        index_status="done",
        lifecycle_state="searchable",
    )
    db_session.add(res)
    db_session.commit()

    db_session.add_all(
        [
            ResourceChunk(
                user_id=user.id,
                resource_id=res.id,
                chunk_index=0,
                page_number=None,
                text="unrelated words only",
                embedding=None,
            ),
            ResourceChunk(
                user_id=user.id,
                resource_id=res.id,
                chunk_index=1,
                page_number=None,
                text="contains exact_quality_token for retrieval",
                embedding=None,
            ),
        ]
    )
    db_session.commit()

    out = retrieve_chunks(db_session, user_id=user.id, query="exact_quality_token", k=2)
    assert len(out) >= 1
    assert "exact_quality_token" in out[0].text
