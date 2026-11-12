import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db",
     "postgresql+psycopg://u:p@h:5432/db"],
)
def test_database_url_usa_psycopg(url):
    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@h:5432/db"
