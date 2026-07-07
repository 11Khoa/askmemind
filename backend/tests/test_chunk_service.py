import pytest

from app.services.chunk_service import ChunkingService
from app.services.extraction.types import ExtractedSource, ExtractedTextUnit


def test_short_creates_one_chunk() -> None:
    source = ExtractedSource(
        source_type="pdf",
        units=[
            ExtractedTextUnit(
                text="Hello world",
                page_number=1,
            ),
        ],
    )

    service = ChunkingService()

    chunks = service.chunk_source(source=source)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "Hello world"
    assert chunks[0].page_number == 1
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 11


def test_long_text_creates_overlaping_chunk() -> None:
    source = ExtractedSource(
        source_type="pdf",
        units=[
            ExtractedTextUnit(
                text="abc123xyz",
                page_number=1,
            ),
        ],
    )

    service = ChunkingService(chunk_size=3, overlap=1)

    chunks = service.chunk_source(source=source)

    assert len(chunks) == 4

    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "abc"
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 3

    assert chunks[1].chunk_index == 1
    assert chunks[1].content == "c12"
    assert chunks[1].start_char == 2
    assert chunks[1].end_char == 5

    assert chunks[2].chunk_index == 2
    assert chunks[2].content == "23x"
    assert chunks[2].start_char == 4
    assert chunks[2].end_char == 7


def test_multiple_units_keep_global_chunk_indexes_and_page_numbers() -> None:
    source = ExtractedSource(
        source_type="pdf",
        units=[
            ExtractedTextUnit(
                text="abcdefghijkl",
                page_number=1,
            ),
            ExtractedTextUnit(
                text="12345",
                page_number=2,
            ),
        ],
    )

    service = ChunkingService(chunk_size=10,overlap=2)

    chunks = service.chunk_source(source=source)

    assert len(chunks) == 3

    assert [chunk.chunk_index for chunk in chunks] == [0,1,2]
    assert [chunk.page_number for chunk in chunks] == [1,1,2]
    assert [chunk.content for chunk in chunks] == [
        "abcdefghij",
        "ijkl",
        "12345",
    ]
    assert [(chunk.start_char, chunk.end_char) for chunk in chunks] == [
        (0,10),
        (8,12),
        (0,5),
    ]


def test_empty_text_units_are_skipped() -> None:
    source = ExtractedSource(
        source_type="pdf",
        units=[
            ExtractedTextUnit(
                text="  ",
                page_number=1
            ),
        ],
    )

    service = ChunkingService()
    chunks = service.chunk_source(source=source)

    assert chunks== []


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [
        (0, 0),
        (10, -1),
        (10, 10),
        (10, 11),
    ],
)
def test_invalid_chunk_config_raises_error(
    chunk_size: int,
    overlap: int,
) -> None:
    with pytest.raises(ValueError):
        ChunkingService(chunk_size=chunk_size, overlap=overlap)


def test_chunk_preserves_unit_metadata_without_sharing_dict_reference() -> None:
    unit_metadata = {"section": "intro"}

    source = ExtractedSource(
        source_type="pdf",
        units=[
            ExtractedTextUnit(
                text="Hello world",
                page_number=1,
                metadata=unit_metadata,
            ),
        ],
    )

    service = ChunkingService()

    chunks = service.chunk_source(source)

    assert chunks[0].metadata == {"section": "intro"}
    assert chunks[0].metadata is not unit_metadata


def test_chunk_preserves_timestamp_citations() -> None:
    source = ExtractedSource(
        source_type="audio",
        units=[
            ExtractedTextUnit(
                text="Transcript segment",
                start_time_seconds=12.5,
                end_time_seconds=18.0,
            ),
        ],
    )

    service = ChunkingService()

    chunks = service.chunk_source(source)

    assert len(chunks) == 1
    assert chunks[0].start_time_seconds == 12.5
    assert chunks[0].end_time_seconds == 18.0
    assert chunks[0].page_number is None