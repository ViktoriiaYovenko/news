from fastapi import FastAPI, Request, Body, JSONResponse
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.param_functions import Query
import requests
import os
from datetime import datetime

API_KEY = "eb1d1e29-f3e5-439a-bd8a-854dedea419d"
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

def get_stock_rating(company, start_date: str, end_date: str):
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
        response = requests.get(BASE_URL, params=params, timeout=5)
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
            "sell": 1 if avg_score < 0 else 0,
            "news": news,
            "news_count": len(news)
        }

    except Exception as e:
        print(f"[ERROR] {company}: {e}")
        return None

def get_external_companies():
    try:
        response = requests.get("https://stin_backend.railway.internal/api/stocks", timeout=5)
        data = response.json()
        return [item["name"] for item in data if "name" in item]
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
    tickers = get_external_companies()
    results = []
    for ticker in tickers:
        result = get_stock_rating(ticker, start, end)
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

@app.get("/liststock", response_class=JSONResponse)
async def liststock(start: str = Query(default="2025-04-01"), end: str = Query(default="2025-04-30")):
    tickers = get_external_companies()
    results = [get_stock_rating(ticker, start, end) for ticker in tickers]
    results = [r for r in results if r]
    return results

@app.get("/recommendations", response_class=JSONResponse)
async def recommendations(start: str = Query(default="2025-04-01"), end: str = Query(default="2025-04-30")):
    tickers = get_external_companies()
    results = []
    for ticker in tickers:
        result = get_stock_rating(ticker, start, end)
        if result:
            results.append({
                "name": result["name"],
                "rating": result["rating"],
                "sell": result["sell"]
            })
    return results

@app.post("/recommendations", response_class=JSONResponse)
async def receive_recommendations(recommendations: dict = Body(...)):
    if not recommendations:
        return {"error": "Нет данных для обработки"}

    processed_recommendations = []
    
    for ticker, data in recommendations.items():
        processed_recommendations.append({
            "name": ticker,
            "declined_last_3_days": data.get("declined_last_3_days", False),
            "more_than_2_declines_last_5_days": data.get("more_than_2_declines_last_5_days", False)
        })
    
    print("Полученные рекомендации:", processed_recommendations)
    
    return {
        "received_recommendations": processed_recommendations,
        "status": "Обработано"
    }

@app.get("/external-stocks", response_class=JSONResponse)
async def external_stocks():
    try:
        tickers = get_external_companies()
        return [{"name": name} for name in tickers]
    except Exception as e:
        return {"error": str(e)}
