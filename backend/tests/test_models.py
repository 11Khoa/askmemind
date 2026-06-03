from sqlalchemy.orm import configure_mappers

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User


def test_sqlalchemy_mapper_configure() -> None:
    configure_mappers()

    assert User is not None
    assert Document is not None
    assert Chunk is not None
