import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import main

client = TestClient(main.app)

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

    # Patch контекстного менеджера и его возвращаемого клиента
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client_instance

        main.positive_words = ["great"]
        main.negative_words = []
        result = await main.get_stock_rating("CompanyX", "2025-04-01", "2025-04-30")
        assert result["name"] == "CompanyX"
        assert result["rating"] == 1
        assert result["news_count"] == 1

@pytest.mark.asyncio
async def test_get_external_companies():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"odeslano": ["A", "B", "C"]}
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client_instance

        companies = await main.get_external_companies()
        assert companies == ["A", "B", "C"]

@pytest.mark.asyncio
async def test_liststock_route(monkeypatch):
    async def mock_get_external_companies():
        return ["AAPL"]

    async def mock_get_stock_rating(company, start, end):
        return {
            "name": company,
            "rating": 5,
            "news": [],
            "news_count": 3,
            "date": "01.01.2025"
        }

    monkeypatch.setattr(main, "get_external_companies", mock_get_external_companies)
    monkeypatch.setattr(main, "get_stock_rating", mock_get_stock_rating)

    response = client.get("/liststock?start=2025-04-01&end=2025-04-30")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.json()[0]["name"] == "AAPL"

@pytest.mark.asyncio
async def test_recommendations_post():
    response = client.post("/recommendations", json={
        "AAPL": {
            "declined_last_3_days": True,
            "more_than_2_declines_last_5_days": False
        }
    })
    assert response.status_code == 200
    assert response.json()["status"] == "Zpracováno"

def test_log_download():
    with open("log.txt", "w") as f:
        f.write("Test log entry")

    response = client.get("/log")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.headers["content-disposition"].startswith("attachment")

@pytest.mark.asyncio
async def test_get_stock_rating_no_articles():
    # Проверка случая, когда статей нет
    mock_data = {
        "articles": {
            "results": []
        }
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value.json.return_value = mock_data
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await main.get_stock_rating("EmptyCorp", "2025-04-01", "2025-04-30")
        assert result is None

@pytest.mark.asyncio
async def test_get_stock_rating_error_handling():
    # Исключение во время запроса
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await main.get_stock_rating("FailCorp", "2025-04-01", "2025-04-30")
        assert result is None

def test_stocks_data_filters_applied(monkeypatch):
    # Проверка фильтрации по hide_negative и hide_lownews
    async def mock_get_external_companies():
        return ["FilteredCorp"]

    async def mock_get_stock_rating(company, start, end):
        return {
            "name": company,
            "rating": -5,  # отрицательный
            "news_count": 2,  # меньше 3
            "date": "01.01.2025",
            "news": []
        }

    monkeypatch.setattr(main, "get_external_companies", mock_get_external_companies)
    monkeypatch.setattr(main, "get_stock_rating", mock_get_stock_rating)

    response = client.get("/stocks-data?hide_negative=1&hide_lownews=1")
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_get_stock_rating_no_articles():
    mock_data = {"articles": {"results": []}}
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value.json.return_value = mock_data
        mock_client_class.return_value.__aenter__.return_value = mock_client
        result = await main.get_stock_rating("EmptyCorp", "2025-04-01", "2025-04-30")
        assert result is None

@pytest.mark.asyncio
async def test_get_stock_rating_error_handling():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection error")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        result = await main.get_stock_rating("FailCorp", "2025-04-01", "2025-04-30")
        assert result is None

def test_stocks_data_filters_applied(monkeypatch):
    async def mock_get_external_companies():
        return ["FilteredCorp"]
    async def mock_get_stock_rating(company, start, end):
        return {"name": company, "rating": -5, "news_count": 2, "date": "01.01.2025", "news": []}
    monkeypatch.setattr(main, "get_external_companies", mock_get_external_companies)
    monkeypatch.setattr(main, "get_stock_rating", mock_get_stock_rating)
    response = client.get("/stocks-data?hide_negative=1&hide_lownews=1")
    assert response.status_code == 200
    assert response.json() == []

def test_recommendations_filter(monkeypatch):
    # убираем фильтры, потому что они не применяются в /recommendations
    async def mock_get_external_companies():
        return ["CorpX"]
    async def mock_get_stock_rating(company, start, end):
        return {"name": company, "rating": -1, "news_count": 2, "date": "01.01.2025", "news": []}
    monkeypatch.setattr(main, "get_external_companies", mock_get_external_companies)
    monkeypatch.setattr(main, "get_stock_rating", mock_get_stock_rating)
    response = client.get("/recommendations")  # БЕЗ hide_negative/lownews
    assert response.status_code == 200
    assert response.json() == [{"name": "CorpX", "rating": -1}]


def test_external_stocks_error_client(monkeypatch):
    async def broken_fetch():
        raise Exception("API failure")

    monkeypatch.setattr(main, "get_external_companies", broken_fetch)

    response = client.get("/external-stocks")
    assert response.status_code == 200
    assert "error" in response.json()
