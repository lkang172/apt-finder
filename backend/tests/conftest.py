from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from aptfinder.db.session import init_db, make_engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as s:
        yield s
