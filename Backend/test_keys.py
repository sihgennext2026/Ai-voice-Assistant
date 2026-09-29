
import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_result(service, status, message=""):
    color = "\033[92m" if status == "PASS" else "\033[91m"
    reset = "\033[0m"
    print(f"{service.ljust(20)}: {color}{status}{reset} {message}")

def test_openrouter():
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        print_result("OpenRouter", "FAIL", "Key not found in .env")
        return

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            timeout=10
        )
        if response.status_code == 200:
            print_result("OpenRouter", "PASS")
        else:
            print_result("OpenRouter", "FAIL", f"Status: {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print_result("OpenRouter", "FAIL", str(e))

def test_tavily():
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        print_result("Tavily", "FAIL", "Key not found in .env")
        return

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"query": "test", "api_key": key},
            timeout=10
        )
        if response.status_code == 200:
            print_result("Tavily", "PASS")
        else:
            print_result("Tavily", "FAIL", f"Status: {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print_result("Tavily", "FAIL", str(e))

def test_serpapi():
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        print_result("SerpAPI", "FAIL", "Key not found in .env")
        return

    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={"q": "test", "api_key": key, "engine": "google"},
            timeout=10
        )
        if response.status_code == 200:
            print_result("SerpAPI", "PASS")
        else:
            print_result("SerpAPI", "FAIL", f"Status: {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print_result("SerpAPI", "FAIL", str(e))

def test_alpha_vantage():
    key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not key:
        print_result("Alpha Vantage", "FAIL", "Key not found in .env")
        return

    try:
        response = requests.get(
            f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey={key}",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if "Global Quote" in data or "Note" in data: # Note means rate limit, which implies auth worked
                print_result("Alpha Vantage", "PASS", "(Rate limit warning)" if "Note" in data else "")
            elif "Error Message" in data:
                 print_result("Alpha Vantage", "FAIL", "Invalid API Key or malformed request")
            else:
                 print_result("Alpha Vantage", "PASS", "(Response received)")
        else:
            print_result("Alpha Vantage", "FAIL", f"Status: {response.status_code}")
    except Exception as e:
        print_result("Alpha Vantage", "FAIL", str(e))

def test_openweather():
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        print_result("OpenWeather", "FAIL", "Key not found in .env")
        return

    try:
        response = requests.get(
            f"http://api.openweathermap.org/data/2.5/weather?q=London&appid={key}",
            timeout=10
        )
        if response.status_code == 200:
            print_result("OpenWeather", "PASS")
        else:
            print_result("OpenWeather", "FAIL", f"Status: {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print_result("OpenWeather", "FAIL", str(e))

def test_sendgrid():
    key = os.getenv("SENDGRID_API_KEY")
    if not key:
        print_result("SendGrid", "FAIL", "Key not found in .env")
        return

    # Using a safe endpoint (get user profile or similar) to verify auth without sending email
    # or just try to send to invalid email and check for auth error vs validation error
    try:
        # Check permissions/scopes is hard, but we can try to access a read-only endpoint?
        # Actually checking 'mail/send' is the only sure way for that scope, but we don't want to spam.
        # Let's try to list API keys or something? No, that requires special scope.
        # Simplest: Try to send with invalid data. If we get 401, key is bad. If we get 400, key is good.
        
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={}, # Empty JSON
            timeout=10
        )
        
        if response.status_code == 401:
             print_result("SendGrid", "FAIL", "Unauthorized (Invalid Key)")
        elif response.status_code == 400:
             print_result("SendGrid", "PASS", "(Auth successful, validation failed as expected)")
        else:
             print_result("SendGrid", "PASS", f"Status: {response.status_code}")

    except Exception as e:
        print_result("SendGrid", "FAIL", str(e))

if __name__ == "__main__":
    print("\n--- Testing API Keys ---\n")
    test_openrouter()
    test_tavily()
    test_serpapi()
    test_alpha_vantage()
    test_openweather()
    test_sendgrid()
    print("\n------------------------\n")
