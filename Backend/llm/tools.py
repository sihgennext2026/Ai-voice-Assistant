
import os
import re
import threading
import requests
from pydantic import BaseModel, Field
from llm.registry import ToolRegistry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Frontend Input Bridge ──────────────────────────────────────────────────────
# Allows tools to pause and wait for user to type a value in the frontend UI.
_input_event = threading.Event()
_input_value: dict = {"value": None}   # shared mutable container
_frontend_callback = None              # set by api.py on startup

def set_frontend_callback(cb):
    """Called once by api.py to give tools access to the WebSocket broadcast."""
    global _frontend_callback
    _frontend_callback = cb

def provide_input(value: str):
    """Called by api.py when the frontend sends a typed input."""
    _input_value["value"] = value
    _input_event.set()

def _request_input_from_frontend(field: str, prompt: str, timeout: int = 120) -> str | None:
    """Emit a request_input event to the frontend and block until reply arrives."""
    _input_event.clear()
    _input_value["value"] = None
    if _frontend_callback:
        _frontend_callback({"type": "request_input", "field": field, "prompt": prompt})
    got = _input_event.wait(timeout=timeout)
    return _input_value["value"] if got else None


def _is_valid_email(addr: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, addr.strip()))

# Initialize Registry
registry = ToolRegistry()

# --- Request Schemas ---

class WebSearchSchema(BaseModel):
    query: str = Field(description="The search query for web intelligence.", default="latest tech news")

class ProductSearchSchema(BaseModel):
    query: str = Field(description="The product name or category to search for.", default="laptop")

class StockMarketSchema(BaseModel):
    symbol: str = Field(description="The stock symbol (e.g., AAPL, GOOGL, TSLA).", default="AAPL")

class WeatherSchema(BaseModel):
    city: str = Field(description="The city name to check weather for.", default="London")

class SendEmailSchema(BaseModel):
    recipient: str = Field(description="The email address of the recipient.", default="example@example.com")
    subject: str = Field(description="The subject of the email.", default="Meeting Reminder")
    body: str = Field(description="The body content of the email.", default="Hi, this is a reminder.")



# --- Tool Implementations ---

@registry.register_function(
    name="web_search",
    description="Search the web for real-time information using Tavily.",
    args_schema=WebSearchSchema
)
def web_search(query: str) -> str:
    """Performs a web search using Tavily API. Optimized for speed."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY not found."
    
    try:
        # Reduced max_resultsMaintained basic depth for speed.
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "query": query, 
                "api_key": api_key, 
                "search_depth": "basic", 
                "include_answer": True,
                "max_results": 3 
            },
            timeout=5 # Strict 5s timeout for voice latency
        )
        
        if response.status_code == 401:
            return "Error: Invalid Tavily API Key. Please check your .env file."
            
        response.raise_for_status()
        data = response.json()
        
        answer = data.get("answer", "")
        results = data.get("results", [])
        formatted_results = "\n".join([f"- {r['title']}: {r['url']}" for r in results[:2]])
        
        # If we have a direct answer, prioritize it
        if answer:
            return f"Answer: {answer}\n(Source: {formatted_results})"
        
        return f"Results:\n{formatted_results}"
    except requests.Timeout:
        return "Search timed out. Please try a simpler query."
    except Exception as e:
        return f"Search failed: {str(e)}"

@registry.register_function(
    name="product_search",
    description="Search for products and prices using SerpAPI (Google Shopping).",
    args_schema=ProductSearchSchema
)
def product_search(query: str) -> str:
    """Searches for products using SerpAPI. Optimized for voice."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return "Error: SERPAPI_API_KEY not found."
    
    try:
        params = {
            "engine": "google_shopping",
            "q": query,
            "api_key": api_key,
            "google_domain": "google.com",
            "gl": "us", # Localization can be dynamic, default to US/IN based on user
            "hl": "en",
            "num": 4 # Fetch fewer results for speed
        }
        response = requests.get("https://serpapi.com/search.json", params=params, timeout=6)
        response.raise_for_status()
        data = response.json()
        
        shopping_results = data.get("shopping_results", [])
        if not shopping_results:
            return "No products found."
            
        formatted = "Found:\n"
        for item in shopping_results[:3]: 
            price = item.get('price') or item.get('extracted_price')
            formatted += f"- {item.get('title')} ({price})\n"
            
        return formatted
    except requests.Timeout:
        return "Product search timed out."
    except Exception as e:
        return f"Search failed: {str(e)}"

@registry.register_function(
    name="get_stock_price",
    description="Get real-time stock market data using Alpha Vantage.",
    args_schema=StockMarketSchema
)
def get_stock_price(symbol: str) -> str:
    """Fetches stock data. Lightweight."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return "Error: ALPHA_VANTAGE_API_KEY not found."
    
    try:
        # Use GLOBAL_QUOTE for lightest weight real-time data
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        quote = data.get("Global Quote", {})
        if not quote:
            return "Symbol not found."
            
        return (f"{quote.get('01. symbol')}: ${quote.get('05. price')} "
                f"({quote.get('10. change percent')})")
    except requests.Timeout:
        return "Stock data unavailable (timeout)."
    except Exception as e:
        return f"Stock error: {str(e)}"

@registry.register_function(
    name="get_weather",
    description="Get current weather for a specific city using OpenWeatherMap.",
    args_schema=WeatherSchema
)
def get_weather(city: str) -> str:
    """Fetches weather data. Fast."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return "Error: OPENWEATHER_API_KEY not found."
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        response = requests.get(url, timeout=4)
        
        if response.status_code == 404:
            return f"City '{city}' not found."
            
        response.raise_for_status()
        data = response.json()
        
        desc = data["weather"][0]["description"]
        temp = round(data["main"]["temp"])
        
        return f"{city}: {desc.capitalize()}, {temp}°C"
    except Exception as e:
        return f"Weather unavailable: {str(e)}"

@registry.register_function(
    name="send_email",
    description="Send an email via SendGrid API.",
    args_schema=SendEmailSchema
)
def send_email(recipient: str, subject: str, body: str) -> str:
    """Sends an email using SendGrid API. If recipient is invalid/placeholder, requests it from the frontend UI."""
    api_key = os.getenv("SENDGRID_API_KEY")
    sender_email = os.getenv("SENDGRID_SENDER_EMAIL")

    if not api_key:
        return "Error: SENDGRID_API_KEY not found."
    if not sender_email:
        return "Error: SENDGRID_SENDER_EMAIL not found."

    # If recipient is a placeholder or not a real email, ask the frontend
    if not _is_valid_email(recipient) or recipient in ("example@example.com", "", "unknown"):
        typed = _request_input_from_frontend(
            field="email",
            prompt=f"Please type the recipient's email address to send: '{subject}'",
        )
        if not typed or not _is_valid_email(typed):
            return "Email cancelled: no valid recipient email address was provided."
        recipient = typed.strip()
    
    url = "https://api.sendgrid.com/v3/mail/send"
    
    payload = {
        "personalizations": [
            {
                "to": [{"email": recipient}]
            }
        ],
        "from": {"email": sender_email},
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": body
            }
        ]
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        
        if response.status_code in [200, 201, 202]:
            return f"Email successfully sent to {recipient}."
        else:
            return f"Failed to send email. Status: {response.status_code}, Response: {response.text}"
            
    except requests.Timeout:
        return "Email sending timed out."
    except Exception as e:
        return f"Email failed: {str(e)}"
