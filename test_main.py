
import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock
import main  



def test_analyze_sentiment_positive():
    main.positive_words = ["good", "great"]
    main.negative_words = []
    assert main.analyze_sentiment("This is a good day") > 0


def test_analyze_sentiment_negative():
    main.positive_words = []
    main.negative_words = ["bad", "terrible"]
    assert main.analyze_sentiment("This is a terrible situation") < 0


def test_analyze_sentiment_mixed():
    main.positive_words = ["nice"]
    main.negative_words = ["awful"]
    score = main.analyze_sentiment("A nice but awful mix")
    assert -10 <= score <= 10


def test_load_words(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("happy\njoyful\n")
    words = main.load_words(str(path))
    assert words == ["happy", "joyful"]


@pytest.mark.asyncio
async def test_get_stock_rating():
    mock_data = {
        "articles": {
            "results": [
                {
                    "title": "Great profit growth",
                    "url": "http://example.com",
                    "source": {"title": "Example News"},
                    "date": "2025-04-01T00:00:00Z"
                }
            ]
        }
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.json.return_value = mock_data
        main.positive_words = ["great"]
        main.negative_words = []
        result = await main.get_stock_rating("CompanyX", "2025-04-01", "2025-04-30")
        assert result["name"] == "CompanyX"
        assert result["rating"] == 1
        assert result["news_count"] == 1


@pytest.mark.asyncio
async def test_get_external_companies():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.json.return_value = {"odeslani": ["A", "B", "C"]}
        companies = await main.get_external_companies()
        assert companies == ["A", "B", "C"]


from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import pytest
from STIN import main

client = TestClient(main.app)

@pytest.mark.asyncio
async def test_liststock_route(monkeypatch):
    async def mock_get_external_companies():
        return ["AAPL"]

    async def mock_get_stock_rating(company, start, end):
        return {"name": company, "rating": 5, "news": [], "news_count": 3, "date": "01.01.2025"}

    monkeypatch.setattr(main, "get_external_companies", mock_get_external_companies)
    monkeypatch.setattr(main, "get_stock_rating", mock_get_stock_rating)

    with TestClient(main.app) as client:
        response = client.get("/liststock?start=2025-04-01&end=2025-04-30")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert response.json()[0]["name"] == "AAPL"


@pytest.mark.asyncio
async def test_recommendations_post():
    with TestClient(main.app) as client:
        response = client.post("/recommendations", json={
            "AAPL": {
                "declined_last_3_days": True,
                "more_than_2_declines_last_5_days": False
            }
        })
        assert response.status_code == 200
        assert response.json()["status"] == "Zpracováno"


def test_log_download():
    response = client.get("/log")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.headers["content-disposition"].startswith("attachment")
