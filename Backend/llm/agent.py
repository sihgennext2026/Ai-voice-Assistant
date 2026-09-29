import json
import os
from pathlib import Path
from typing import Generator, List, Dict, Any

from llm.provider import LangChainProvider
from llm.controller import ExecutionController
from llm.tools import registry

# Constant System Prompt
SYSTEM_PROMPT = '''You are RAGAVA, the Autonomous Voice Agent, a highly advanced and capable AI assistant.
Your goal is to be a helpful, resource-rich, and intelligent companion. You have access to real-time tools for web search, e-commerce, financial data, weather, and email.

VOICE & STYLE:
- Speak naturally, confidently, and concisely. 
- Avoid robotic phrasing. Use a conversational tone.
- Keep responses short (1-2 sentences) unless detailing specific data (like stock specs or search results).
- If listing information, be brief and summarize.

CAPABILITIES & TOOLS:
1. Web Intelligence (Tavily): Use 'web_search' for current events, news, or general knowledge deeper than your training data.
2. E-Commerce (SerpAPI): Use 'product_search' to find products, prices, and shopping deals.
3. Financial Markets (Alpha Vantage): Use 'get_stock_price' for real-time stock quotes and market data.
4. Environmental Context (OpenWeather): Use 'get_weather' for current conditions in any city.
5. Real-World Action (Email): Use 'send_email' to send messages. Ask for recipient and content if not provided.

BEHAVIOR:
- When asked a question, determine if a tool is needed.
- If a tool is needed, call it silently. Do not narrate "I am calling the tool".
- Interpret the tool output and speak the result naturally.
- If a tool fails, explain simply and ask to try again or move on.
- For sensitive actions (like sending email), confirm the details before acting if strictly necessary, but prefer efficiency.
- Maintain context. If the user asks "What about Apple?" after discussing stocks, assume they mean AAPL stock.



IMPORTANT ADVISORY:
- You have NO internal knowledge of current events, prices, or real-time data.
- You MUST use 'web_search' or other tools for ANY query about news, people, companies, or facts.
- Do NOT answer from your own training data. Always verify with a tool.
- If asking about a person (like "President of USA"), ALWAYS use 'web_search' to get the latest info.

Make every interaction feel seamless, premium, and intelligent and use indian standards like kilograms , literes , Rupees.
'''

HISTORY_FILE = Path(__file__).parent / "history.json"

def load_history() -> List[Dict[str, Any]]:
    """Loads conversation history from JSON file."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load history: {e}")
            return []
    return []

def save_history(history: List[Dict[str, Any]]):
    """Saves conversation history to JSON file."""
    try:
        # We only save the last 20 turns to keep context manageable
        trimmed_history = history[-20:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed_history, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save history: {e}")

def clear_history():
    """Clears the history file."""
    if HISTORY_FILE.exists():
        try:
            os.remove(HISTORY_FILE)
            print("Conversation history cleared.")
        except Exception as e:
            print(f"Warning: Failed to clear history: {e}")

def run_agent(user_input: str) -> Generator[str, None, None]:
    """
    Main generator for the voice agent using the new Execution Controller.
    """
    # 1. Initialize Components
    # In a real app, you might want to instantiate these once globally, 
    # In a real app, you might want to instantiate these once globally, 
    # but for this script structure, we do it here.
    # explicit model selection as per user request
    provider = LangChainProvider(model_name="sao10k/l3-lunaris-8b") 
    controller = ExecutionController(provider, registry)
    
    # 2. Handle admin commands
    if user_input.lower().strip() == "clear":
        clear_history()
        yield "History cleared."
        return

    # 3. Load History
    history = load_history()
    
    # 4. Run Controller
    # The controller yields strings for TTS
    # It also manages the 'Turn' logic internally for tool calls
    
    # We need to capture the updated history from the controller's run
    # However, since controller yields strings, we need a way to get the state back.
    # The provided controller design in the previous step didn't explicitly return state.
    # We will modify the interaction slightly here or assume the controller modifies a passed list?
    # Actually, let's keep it simple: We will reconstruct the history based on what happened.
    # BUT, strict adherence to the new architecture is required.
    
    # Let's adjust usage:
    # The controller yields chunks. We wrap it to catch the chunks.
    # State management is a bit tricky with generators. 
    # Let's trust the controller to do its job for this turn.
    # BUT we need to persist the conversation.
    
    # Refined approach: 
    # We pass the history list to the controller. The controller appends to it in-place (because lists are mutable).
    # Then we save it.
    
    # Refined approach: 
    # We pass the history list to the controller.
    # We execute it once, yield the results, and capture them for history.
    
    # Update history with user input
    history.append({"role": "user", "content": user_input})
    
    # Run Controller
    # It yields content strings.
    runner = controller.run(user_input, history[:-1], SYSTEM_PROMPT) 
    
    full_response = ""
    for chunk in runner:
        # Pass through control signals but don't save to history
        if "[MUSIC_START]" in chunk or "[MUSIC_STOP]" in chunk:
            yield chunk
            continue
            
        full_response += chunk
        yield chunk
        
    history.append({"role": "assistant", "content": full_response})
    save_history(history)
