"""Chapter/section navigation works across textbook contents formats.

Two real books in use format their contents pages differently: one prints a page
number after every entry ("1.2Random sampling 4"), the other prints none at all
and numbers chapters bare ("1 Matrices and Systems of Equations"). Only the
former used to be detected, so the second book showed no navigation whatsoever.
"""

from __future__ import annotations

from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.models.user import User
from app.services.resource_sections import list_resource_sections

# Leon, "Linear Algebra with Applications": no page numbers, bare chapters.
NO_PAGE_NUMBER_CONTENTS = """Contents
Preface
1 Matrices and Systems of Equations
1.1 Systems of Linear Equations
1.2 Row Echelon Form
1.3 Matrix Arithmetic
MATLAB Exercises
Chapter Test A —True or False
2 Determinants
2.1 The Determinant of a Matrix
2.2 Properties of Determinants
"""

# The same book's body headings: section number, no period, no page number.
NO_PAGE_NUMBER_BODY = {
    23: "1.1 Systems of Linear Equations\nA linear equation in n unknowns is...",
    49: "1.2 Row Echelon Form\nIn Section 1 we learned a method for reducing...",
    90: "1.3 Matrix Arithmetic\nIn this section we introduce the standard...",
    245: "2.1 The Determinant of a Matrix\nWith each square matrix it is possible...",
    263: "2.2 Properties of Determinants\nIn this section we consider the effects...",
}

# Durrett-style contents, which already worked: printed page after each entry.
PAGE_NUMBERED_CONTENTS = """Contents
Chapter 1Experiments with random outcomes 1
1.1Sample spaces and probabilities 1
1.2Random sampling 4
1.3Infinitely many outcomes 8
"""

PAGE_NUMBERED_BODY = {
    16: "1.1. Sample spaces and probabilities 1\nWe begin with the notion of...",
    19: "1.2. Random sampling 4\nSuppose we choose an object at random...",
}


def _seed_pages(db, pages: list[tuple[int, str]]) -> tuple[User, Resource]:
    """Seed a PDF whose chunks are the given (page_number, text) pairs, in order."""
    user = User(email="reader@example.com", password_hash="x")
    db.add(user)
    db.flush()

    resource = Resource(
        user_id=user.id,
        title="textbook.pdf",
        original_filename="textbook.pdf",
        mime_type="application/pdf",
    )
    db.add(resource)
    db.flush()

    for index, (page, text) in enumerate(pages):
        db.add(
            ResourceChunk(
                user_id=user.id,
                resource_id=resource.id,
                chunk_index=index,
                page_number=page,
                text=text,
            )
        )
    db.flush()
    return user, resource


def _seed(db, *, contents: str, body: dict[int, str]) -> tuple[User, Resource]:
    # Contents sits in the front matter, body headings follow in page order.
    return _seed_pages(db, [(18, contents), *sorted(body.items())])


def test_contents_without_page_numbers_still_yields_sections(db_session):
    user, resource = _seed(
        db_session, contents=NO_PAGE_NUMBER_CONTENTS, body=NO_PAGE_NUMBER_BODY
    )

    sections = list_resource_sections(db_session, user=user, resource_id=resource.id)

    keys = [s.key for s in sections]
    assert "1.1" in keys
    assert "2.2" in keys
    # Both chapters are found even though the contents never says "Chapter".
    assert "ch1" in keys
    assert "ch2" in keys

    by_key = {s.key: s for s in sections}
    assert by_key["1.1"].title == "Systems of Linear Equations"
    assert by_key["ch1"].title == "Matrices and Systems of Equations"
    assert by_key["ch1"].kind == "chapter"
    assert by_key["1.1"].kind == "section"


def test_body_pages_are_found_without_a_period_after_the_number(db_session):
    user, resource = _seed(
        db_session, contents=NO_PAGE_NUMBER_CONTENTS, body=NO_PAGE_NUMBER_BODY
    )

    by_key = {
        s.key: s
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    assert by_key["1.1"].page_start == 23
    assert by_key["1.2"].page_start == 49
    assert by_key["2.1"].page_start == 245


def test_a_chapter_starts_where_its_first_section_does(db_session):
    user, resource = _seed(
        db_session, contents=NO_PAGE_NUMBER_CONTENTS, body=NO_PAGE_NUMBER_BODY
    )

    by_key = {
        s.key: s
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    # Chapter openers do not repeat their number as a heading, so they inherit
    # the page of section 1 rather than being left unnavigable.
    assert by_key["ch1"].page_start == 23
    assert by_key["ch2"].page_start == 245


def test_sections_are_ordered_by_chapter_then_number(db_session):
    user, resource = _seed(
        db_session, contents=NO_PAGE_NUMBER_CONTENTS, body=NO_PAGE_NUMBER_BODY
    )

    keys = [
        s.key
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    ]

    assert keys.index("ch1") < keys.index("1.1") < keys.index("1.2") < keys.index("ch2")
    assert keys.index("ch2") < keys.index("2.1")


def test_contents_prose_does_not_become_a_section(db_session):
    user, resource = _seed(
        db_session, contents=NO_PAGE_NUMBER_CONTENTS, body=NO_PAGE_NUMBER_BODY
    )

    titles = [
        s.title.lower()
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    ]

    # Unnumbered contents lines are not sections.
    assert not any("matlab" in t for t in titles)
    assert not any("chapter test" in t for t in titles)
    assert not any("preface" in t for t in titles)


def test_page_numbered_contents_keeps_working(db_session):
    user, resource = _seed(
        db_session, contents=PAGE_NUMBERED_CONTENTS, body=PAGE_NUMBERED_BODY
    )

    by_key = {
        s.key: s
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    assert by_key["ch1"].title == "Experiments with random outcomes"
    assert by_key["1.1"].title == "Sample spaces and probabilities"
    # Anchored on the body heading, not the printed page.
    assert by_key["1.1"].page_start == 16
    assert by_key["1.2"].page_start == 19
    # Entries with no body match are still placed via the printed-page offset.
    assert by_key["1.3"].page_start is not None


def test_sections_listed_overleaf_resolve_to_the_body_not_the_contents(db_session):
    """
    Only the first page of a multi-page contents carries the word "Contents".

    Entries listed on the pages after it used to resolve to the contents page,
    because that was the only page the body scan knew to skip — so jumping to
    section 3.2 landed you back in the table of contents.
    """
    user, resource = _seed_pages(
        db_session,
        [
            (
                18,
                "Contents\nPreface\n1 Matrices and Systems of Equations\n"
                "1.1 Systems of Linear Equations\n1.2 Row Echelon Form\n",
            ),
            # Overleaf: same formatting, but no "Contents" heading.
            (
                19,
                "3 Vector Spaces\n3.1 Definition and Examples\n3.2 Subspaces\n"
                "3.3 Linear Independence\n",
            ),
            (23, "1.1 Systems of Linear Equations\nA linear equation in n unknowns"),
            (310, "3.1 Definition and Examples\nIn this section we present the formal"),
            (335, "3.2 Subspaces\nGiven a vector space V, it is often possible to"),
            (372, "3.3 Linear Independence\nIn this section we look more closely at"),
        ],
    )

    by_key = {
        s.key: s
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    assert by_key["3.1"].page_start == 310
    assert by_key["3.2"].page_start == 335
    assert by_key["3.3"].page_start == 372
    # The chapter opener follows its first section into the body.
    assert by_key["ch3"].page_start == 310


def test_running_headers_do_not_become_chapters(db_session):
    """Body pages head with "<page number> <chapter title>", not a chapter entry."""
    user, resource = _seed(
        db_session,
        contents=NO_PAGE_NUMBER_CONTENTS,
        body={
            23: "1.1 Systems of Linear Equations\nA linear equation in n unknowns...",
            120: "120 Matrices and Systems of Equations\nmore prose about matrices",
            256: "256 Determinants\nprose about determinants continues here",
        },
    )

    keys = {
        s.key
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    # Only the two chapters the contents actually lists.
    assert {k for k in keys if k.startswith("ch")} == {"ch1", "ch2"}
    assert "ch120" not in keys
    assert "ch256" not in keys


def test_the_answer_key_at_the_back_is_not_mistaken_for_sections(db_session):
    """Answers are numbered like sections: "2.13 A and B are independent"."""
    user, resource = _seed(
        db_session,
        contents=NO_PAGE_NUMBER_CONTENTS,
        body={
            23: "1.1 Systems of Linear Equations\nA linear equation in n unknowns...",
            429: "2.13 AandBare independent\n3.49 F(x)=1\n4.19 LetXbe the number of people",
            431: "5.21 MY(t)=ebtMX(at)\n6.13 The random variables are not independent",
        },
    )

    keys = {
        s.key
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    for answer in ("2.13", "3.49", "4.19", "5.21", "6.13"):
        assert answer not in keys, f"answer {answer} leaked in as a section"


def test_decimals_in_mathematical_prose_are_not_sections(db_session):
    """Bodies are full of "0.40", "2.25 ○ 4=8" and "(6.5 ) This decomposition"."""
    user, resource = _seed(
        db_session,
        contents=NO_PAGE_NUMBER_CONTENTS,
        body={
            23: "1.1 Systems of Linear Equations\nthe matrix entries are 0.40\n0.20",
            118: "0.25 0.30 0.50\n2.25 ○ 4=[[2.25]]-4=2-4=8\n6.5 ) This decomposition can be used",
            131: "12.1\n0.7\n0.28 0.33 0.19",
        },
    )

    keys = {
        s.key
        for s in list_resource_sections(db_session, user=user, resource_id=resource.id)
    }

    for noise in ("0.25", "2.25", "6.5", "12.1", "0.40", "0.28"):
        assert noise not in keys
