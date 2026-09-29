
# API Key Setup for Autonomous Voice Agent

To fully enable the new capabilities (Web Search, E-Commerce, Finance, Weather, Email), you need to add the following keys to your `.env` file in `C:\Autonomus voice agent\Backend\.env`.

## Required Keys

1.  **Web Intelligence (Tavily)**
    *   Get Key: https://tavily.com/
    *   Add: `TAVILY_API_KEY=tvly-xxxxxxxx`

2.  **E-Commerce (SerpAPI)**
    *   Get Key: https://serpapi.com/
    *   Add: `SERPAPI_API_KEY=xxxxxxxx`

3.  **Financial Markets (Alpha Vantage)**
    *   Get Key: https://www.alphavantage.co/support/#api-key
    *   Add: `ALPHA_VANTAGE_API_KEY=xxxxxxxx`

4.  **Environmental Context (OpenWeatherMap)**
    *   Get Key: https://openweathermap.org/api
    *   Add: `OPENWEATHER_API_KEY=xxxxxxxx`

5.  **Real-World Action (SendGrid Email)**
    *   Get Key: https://app.sendgrid.com/settings/api_keys
    *   Verify Sender: https://app.sendgrid.com/settings/sender_auth
    *   Add: `SENDGRID_API_KEY=SG.xxxxxxxx`
    *   Add: `SENDGRID_SENDER_EMAIL=verified_sender@example.com`

## Example .env File

```env
OPENROUTER_API_KEY=sk-or-xxxx
TAVILY_API_KEY=tvly-xxxx
SERPAPI_API_KEY=xxxx
ALPHA_VANTAGE_API_KEY=xxxx
OPENWEATHER_API_KEY=xxxx
SENDGRID_API_KEY=SG.xxxx
SENDGRID_SENDER_EMAIL=me@example.com
```
