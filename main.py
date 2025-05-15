from fastapi import FastAPI, Request, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import os
import httpx
import logging
from fastapi.responses import FileResponse

logging.basicConfig(
    filename="log.txt",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

API_KEY = "2493ec50-b5cb-40ba-a42a-a91a6f185564"
BASE_URL = "https://newsapi.ai/api/v1/article/getArticles"
MIN_ARTICLES_REQUIRED = 3

app = FastAPI()
templates = Jinja2Templates(directory="templates")


def load_words(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


positive_words = load_words("positive_words.txt")
negative_words = load_words("negative_words.txt")


def analyze_sentiment(title):
    title_lower = title.lower()
    score = 0
    for word in positive_words:
        if word in title_lower:
            score += 1
    for word in negative_words:
        if word in title_lower:
            score -= 1
    return max(min(score, 10), -10)


async def get_stock_rating(company, start_date: str, end_date: str):
    params = {
        "apiKey": API_KEY,
        "keyword": company,
        "lang": "eng",
        "publishedAtStart": start_date,
        "publishedAtEnd": end_date,
        "sortBy": "date",
        "resultType": "articles",
        "articlesPage": 1,
        "articlesCount": 10
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(BASE_URL, params=params)
            data = response.json()

        articles = data.get("articles", {}).get("results", [])

        if not articles:
            return None

        news = []
        total_score = 0

        for article in articles:
            title = article["title"]
            score = analyze_sentiment(title)
            total_score += score
            pub_date = datetime.strptime(article["date"][:10], "%Y-%m-%d").strftime("%d.%m.%Y")
            news.append({
                "title": title,
                "url": article["url"],
                "source": article["source"]["title"],
                "date": pub_date,
                "score": score
            })

        avg_score = total_score // len(news)
        return {
            "name": company,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "rating": avg_score,
            "news": news,
            "news_count": len(news)
        }

    except Exception as e:
        print(f"[ERROR] {company}: {e}")
        return None


async def get_external_companies():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post("https://stinbackend-production.up.railway.app/api/stocks/recommend")
            data = response.json()
            return data.get("odeslano", [])
    except Exception as e:
        print(f"[ERROR] external company fetch: {e}")
        return []


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    start: str = Query(default="2025-04-01"),
    end: str = Query(default="2025-04-30"),
    hide_negative: int = Query(default=0),
    hide_lownews: int = Query(default=0)
):
    tickers = await get_external_companies()
    results = []
    for ticker in tickers:
        result = await get_stock_rating(ticker, start, end)
        if not result:
            continue
        if hide_lownews and result["news_count"] < MIN_ARTICLES_REQUIRED:
            continue
        if hide_negative and result["rating"] < 0:
            continue
        results.append(result)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "stocks": results,
        "start": start,
        "end": end,
        "hide_negative": hide_negative,
        "hide_lownews": hide_lownews
    })
@app.get("/stocks-data", response_class=JSONResponse)
async def stocks_data(start: str = Query(default="2025-04-01"),
                      end: str = Query(default="2025-04-30"),
                      hide_negative: int = Query(default=0),
                      hide_lownews: int = Query(default=0)):
    tickers = await get_external_companies()
    results = []
    for ticker in tickers:
        result = await get_stock_rating(ticker, start, end)
        if not result:
            continue
        if hide_lownews and result["news_count"] < MIN_ARTICLES_REQUIRED:
            continue
        if hide_negative and result["rating"] < 0:
            continue
        results.append({
            "name": result["name"],
            "date": result["date"],
            "rating": result["rating"],
        })
    return results


@app.get("/liststock", response_class=JSONResponse)
async def liststock(start: str = Query(default="2025-04-01"), end: str = Query(default="2025-04-30")):
    tickers = await get_external_companies()
    results = [await get_stock_rating(ticker, start, end) for ticker in tickers]
    return [r for r in results if r]


@app.get("/recommendations", response_class=JSONResponse)
async def recommendations(start: str = Query(default="2025-04-01"), end: str = Query(default="2025-04-30")):
    tickers = await get_external_companies()
    results = []
    for ticker in tickers:
        result = await get_stock_rating(ticker, start, end)
        if result:
            results.append({
                "name": result["name"],
                "rating": result["rating"],
            })
    return results


@app.post("/recommendations", response_class=JSONResponse)
async def receive_recommendations(recommendations: dict = Body(...)):
    if not recommendations:
        return {"error": "Žádná data ke zpracování"}

    processed_recommendations = []

    for ticker, data in recommendations.items():
        processed_recommendations.append({
            "name": ticker,
            "declined_last_3_days": data.get("declined_last_3_days", False),
            "more_than_2_declines_last_5_days": data.get("more_than_2_declines_last_5_days", False)
        })

    print("Obdržená doporučení:", processed_recommendations)

    return {
        "received_recommendations": processed_recommendations,
        "status": "Zpracováno"
    }


@app.get("/external-stocks", response_class=JSONResponse)
async def external_stocks():
    try:
        tickers = await get_external_companies()
        return [{"name": name} for name in tickers]
    except Exception as e:
        return {"error": str(e)}
    
@app.get("/log", response_class=FileResponse)
async def download_log():
    return FileResponse("log.txt", media_type="text/plain", filename="log.txt")
    
