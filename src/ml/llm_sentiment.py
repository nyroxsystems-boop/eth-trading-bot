"""
LLM-based Sentiment Analysis for Crypto News
Uses Claude/GPT API to analyze market sentiment from news and social media
"""

import os
import asyncio
import json
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import aiohttp

# Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")


@dataclass
class SentimentResult:
    """Result of sentiment analysis"""
    score: float  # -1.0 (bearish) to 1.0 (bullish)
    confidence: float  # 0.0 to 1.0
    summary: str
    key_topics: List[str]
    source: str
    timestamp: str


@dataclass
class NewsItem:
    """News item for analysis"""
    title: str
    description: str
    source: str
    published_at: str
    url: str
    currencies: List[str]


class NewsFetcher:
    """Fetch crypto news from various sources"""
    
    def __init__(self):
        self.cryptopanic_url = "https://cryptopanic.com/api/v1/posts/"
    
    async def fetch_cryptopanic(self, currency: str = "ETH", limit: int = 10) -> List[NewsItem]:
        """Fetch news from CryptoPanic API"""
        if not CRYPTOPANIC_API_KEY:
            print("⚠️ CRYPTOPANIC_API_KEY not set - using mock data")
            return self._get_mock_news()
        
        try:
            params = {
                "auth_token": CRYPTOPANIC_API_KEY,
                "currencies": currency,
                "filter": "hot",
                "public": "true"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.cryptopanic_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        news_items = []
                        
                        for item in data.get("results", [])[:limit]:
                            news_items.append(NewsItem(
                                title=item.get("title", ""),
                                description=item.get("title", ""),  # CryptoPanic uses title as desc
                                source=item.get("source", {}).get("title", "Unknown"),
                                published_at=item.get("published_at", ""),
                                url=item.get("url", ""),
                                currencies=[c.get("code", "") for c in item.get("currencies", [])]
                            ))
                        
                        return news_items
                    else:
                        print(f"⚠️ CryptoPanic API error: {response.status}")
                        return self._get_mock_news()
                        
        except Exception as e:
            print(f"❌ Error fetching news: {e}")
            return self._get_mock_news()
    
    def _get_mock_news(self) -> List[NewsItem]:
        """Return mock news for testing"""
        return [
            NewsItem(
                title="Ethereum ETF sees record inflows as institutional interest grows",
                description="Major institutions continue to accumulate ETH following spot ETF approval",
                source="CoinDesk",
                published_at=datetime.now().isoformat(),
                url="https://example.com/news/1",
                currencies=["ETH"]
            ),
            NewsItem(
                title="Ethereum network upgrade scheduled for Q2 2026",
                description="The Pectra upgrade promises 10x lower gas fees and improved scalability",
                source="The Block",
                published_at=datetime.now().isoformat(),
                url="https://example.com/news/2",
                currencies=["ETH"]
            ),
            NewsItem(
                title="DeFi TVL reaches new ATH with Ethereum leading the charge",
                description="Total value locked in DeFi protocols surpasses $200B milestone",
                source="DefiLlama",
                published_at=datetime.now().isoformat(),
                url="https://example.com/news/3",
                currencies=["ETH"]
            )
        ]


class LLMSentimentAnalyzer:
    """
    Analyze crypto news and social media sentiment using LLMs
    Supports Claude (Anthropic) and GPT (OpenAI)
    """
    
    def __init__(self, provider: str = "anthropic"):
        self.provider = provider
        self.news_fetcher = NewsFetcher()
        self._cache: Dict[str, SentimentResult] = {}
        self._cache_ttl = timedelta(minutes=15)
    
    async def analyze_headlines(self, headlines: List[str]) -> SentimentResult:
        """
        Analyze a list of headlines and return overall sentiment
        """
        if not headlines:
            return SentimentResult(
                score=0.0,
                confidence=0.0,
                summary="No headlines to analyze",
                key_topics=[],
                source="none",
                timestamp=datetime.now().isoformat()
            )
        
        # Check cache
        cache_key = hash(tuple(headlines[:5]))  # Use first 5 headlines as cache key
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # Check if cache is still valid
            cached_time = datetime.fromisoformat(cached.timestamp)
            if datetime.now() - cached_time < self._cache_ttl:
                return cached
        
        # Build prompt
        headlines_text = "\n".join([f"- {h}" for h in headlines[:10]])
        
        prompt = f"""Analyze the following crypto/Ethereum news headlines and provide a trading sentiment assessment.

Headlines:
{headlines_text}

Please respond in JSON format with these fields:
- score: A number from -1.0 (extremely bearish) to 1.0 (extremely bullish)
- confidence: Your confidence level from 0.0 to 1.0
- summary: A brief 1-2 sentence summary of the overall market sentiment
- key_topics: An array of 3-5 key topics mentioned
- recommendation: One of "strong_buy", "buy", "hold", "sell", "strong_sell"

Focus on factors that would affect ETH price in the next 1-24 hours."""

        try:
            if self.provider == "anthropic" and ANTHROPIC_API_KEY:
                result = await self._call_anthropic(prompt)
            elif self.provider == "openai" and OPENAI_API_KEY:
                result = await self._call_openai(prompt)
            else:
                # Fallback to rule-based analysis
                result = self._rule_based_analysis(headlines)
            
            # Cache result
            self._cache[cache_key] = result
            return result
            
        except Exception as e:
            print(f"❌ LLM Analysis error: {e}")
            return self._rule_based_analysis(headlines)
    
    async def _call_anthropic(self, prompt: str) -> SentimentResult:
        """Call Claude API for sentiment analysis"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                
                payload = {
                    "model": "claude-3-haiku-20240307",  # Fast and cheap
                    "max_tokens": 500,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data["content"][0]["text"]
                        
                        # Parse JSON from response
                        json_start = content.find("{")
                        json_end = content.rfind("}") + 1
                        if json_start >= 0 and json_end > json_start:
                            result_data = json.loads(content[json_start:json_end])
                            
                            return SentimentResult(
                                score=float(result_data.get("score", 0)),
                                confidence=float(result_data.get("confidence", 0.5)),
                                summary=result_data.get("summary", ""),
                                key_topics=result_data.get("key_topics", []),
                                source="anthropic",
                                timestamp=datetime.now().isoformat()
                            )
                    
                    raise Exception(f"Anthropic API error: {response.status}")
                    
        except Exception as e:
            print(f"❌ Anthropic API error: {e}")
            raise
    
    async def _call_openai(self, prompt: str) -> SentimentResult:
        """Call OpenAI API for sentiment analysis"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a crypto market analyst."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3
                }
                
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data["choices"][0]["message"]["content"]
                        
                        # Parse JSON from response
                        json_start = content.find("{")
                        json_end = content.rfind("}") + 1
                        if json_start >= 0 and json_end > json_start:
                            result_data = json.loads(content[json_start:json_end])
                            
                            return SentimentResult(
                                score=float(result_data.get("score", 0)),
                                confidence=float(result_data.get("confidence", 0.5)),
                                summary=result_data.get("summary", ""),
                                key_topics=result_data.get("key_topics", []),
                                source="openai",
                                timestamp=datetime.now().isoformat()
                            )
                    
                    raise Exception(f"OpenAI API error: {response.status}")
                    
        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            raise
    
    def _rule_based_analysis(self, headlines: List[str]) -> SentimentResult:
        """
        Fallback rule-based sentiment analysis when LLM is unavailable
        """
        bullish_keywords = [
            "surge", "rally", "breakout", "bullish", "gains", "soars", "jumps",
            "record", "ath", "institutional", "adoption", "approval", "upgrade",
            "etf", "positive", "growth", "inflow", "accumulation"
        ]
        
        bearish_keywords = [
            "crash", "plunge", "bearish", "drops", "falls", "dump", "sell-off",
            "hack", "exploit", "regulation", "ban", "warning", "outflow",
            "liquidation", "fear", "panic", "negative"
        ]
        
        bullish_count = 0
        bearish_count = 0
        topics = set()
        
        for headline in headlines:
            headline_lower = headline.lower()
            
            for kw in bullish_keywords:
                if kw in headline_lower:
                    bullish_count += 1
                    topics.add(kw)
            
            for kw in bearish_keywords:
                if kw in headline_lower:
                    bearish_count += 1
                    topics.add(kw)
        
        # Calculate score (-1 to 1)
        total = bullish_count + bearish_count
        if total > 0:
            score = (bullish_count - bearish_count) / total
            confidence = min(0.3 + (total * 0.1), 0.7)  # Max 0.7 for rule-based
        else:
            score = 0.0
            confidence = 0.1
        
        # Generate summary
        if score > 0.3:
            summary = "Market sentiment appears bullish based on recent headlines."
        elif score < -0.3:
            summary = "Market sentiment appears bearish based on recent headlines."
        else:
            summary = "Market sentiment is neutral/mixed based on recent headlines."
        
        return SentimentResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            summary=summary,
            key_topics=list(topics)[:5],
            source="rule_based",
            timestamp=datetime.now().isoformat()
        )
    
    async def get_market_sentiment(self, currency: str = "ETH") -> SentimentResult:
        """
        Get overall market sentiment for a currency
        Fetches news and analyzes with LLM
        """
        # Fetch recent news
        news = await self.news_fetcher.fetch_cryptopanic(currency)
        headlines = [item.title for item in news]
        
        # Analyze sentiment
        return await self.analyze_headlines(headlines)


# Singleton instance
_sentiment_analyzer: Optional[LLMSentimentAnalyzer] = None

def get_sentiment_analyzer() -> LLMSentimentAnalyzer:
    """Get or create sentiment analyzer instance"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        # Prefer Anthropic, fallback to OpenAI
        provider = "anthropic" if ANTHROPIC_API_KEY else "openai"
        _sentiment_analyzer = LLMSentimentAnalyzer(provider=provider)
    return _sentiment_analyzer


# Quick test
if __name__ == "__main__":
    async def test():
        analyzer = get_sentiment_analyzer()
        result = await analyzer.get_market_sentiment("ETH")
        
        print(f"\n📊 Market Sentiment Analysis:")
        print(f"   Score: {result.score:.2f} ({'+' if result.score > 0 else ''}{result.score:.0%})")
        print(f"   Confidence: {result.confidence:.0%}")
        print(f"   Summary: {result.summary}")
        print(f"   Topics: {', '.join(result.key_topics)}")
        print(f"   Source: {result.source}")
    
    asyncio.run(test())
