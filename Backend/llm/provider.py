import os
import re
import json
from dotenv import load_dotenv
import logging
from typing import List, Dict, Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from pydantic import ValidationError

from llm.interfaces import LLMProviderInterface, ToolInterface
from llm.schemas import AgentOutput

class LangChainProvider(LLMProviderInterface):
    """
    Implementation of LLMProviderInterface using LangChain's ChatOpenAI.
    Uses 'with_structured_output' to strictly enforce AgentOutput schema.
    """
    def __init__(self, model_name: str = "sao10k/l3-lunaris-8b", temperature: float = 0.0):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            # Fallback or error
            pass
            
        self.base_url = "https://openrouter.ai/api/v1"
        self.base_url = "https://openrouter.ai/api/v1"
        self.model_name = model_name

        # Initialize the raw LLM
        self.raw_llm = ChatOpenAI(
            model=self.model_name,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            temperature=temperature,
        )

    def generate(self, messages: List[Dict[str, Any]], tools: Optional[List[ToolInterface]] = None) -> AgentOutput:
        """
        Generates a structured response.
        Uses explicit prompting and robust JSON parsing to handle model outputs efficiently.
        """
        
        # 1. Convert dict messages to LangChain messages format
        lc_messages = self._convert_messages(messages)
        
        # 2. Construct System Prompt with Schema and Tools
        schema_instruction = (
            "\nYou are an AI assistant. You must strictly output in valid JSON format. Do not add any text before or after the JSON.\n"
            "The JSON output must adhere to the following schema:\n"
            "{\n"
            '  "thought": "Internal reasoning about what to do next",\n'
            '  "type": "response" | "tool_call",\n'
            '  "content": "string (the actual response to speak to the user, leave empty if calling tool)",\n'
            '  "tool_name": "string (name of tool to call, only if type is tool_call)",\n'
            '  "arguments": { ... } (arguments for the tool, only if type is tool_call)\n'
            "}\n"
        )
        
        tool_instruction = ""
        if tools:
            tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])
            tool_instruction = (
                f"\n\nAvailable Tools:\n{tool_descriptions}\n\n"
                "If you need to use a tool, set 'type' to 'tool_call', 'tool_name' to the name of the tool, "
                "and 'arguments' to the tool arguments.\n"
                "If you want to speak to the user, set 'type' to 'response' and 'content' to your message.\n\n"
                "EXAMPLES:\n"
                "User: 'What is the price of Apple stock?'\n"
                "Assistant: {\"thought\": \"User is asking for stock price.\", \"type\": \"tool_call\", \"tool_name\": \"get_stock_price\", \"arguments\": {\"symbol\": \"AAPL\"}, \"content\": \"\"}\n\n"
                "User: 'Who is the president of France?'\n"
                "Assistant: {\"thought\": \"Checking current political figures.\", \"type\": \"tool_call\", \"tool_name\": \"web_search\", \"arguments\": {\"query\": \"current president of France\"}, \"content\": \"\"}\n\n"
                "User: 'Hello there.'\n"
                "Assistant: {\"thought\": \"Greeting the user.\", \"type\": \"response\", \"content\": \"Hello! How can I help you today?\"}\n"
            )
        
        system_update = schema_instruction + tool_instruction
        
        # Insert/Update System Message
        if lc_messages and isinstance(lc_messages[0], SystemMessage):
            lc_messages[0].content += system_update
        else:
            lc_messages.insert(0, SystemMessage(content=system_update))

        try:
            # 3. Invoke Raw LLM
            response = self.raw_llm.invoke(lc_messages)
            response_content = response.content
            
            # 4. Clean and Parse JSON
            cleaned_content = self._extract_json(response_content)
            
            try:
                data = json.loads(cleaned_content)
                # Remove 'thought' field if present to match strict schema, or log it
                if "thought" in data:
                    logger.debug(f"Agent Thought: {data['thought']}")
                    del data["thought"]
                    
                # Validate against Pydantic model
                return AgentOutput(**data)
            except (json.JSONDecodeError, ValidationError) as parse_err:
                # 5. Fallback: Try to rescue a 'content' field before giving up
                logger.warning(f"Failed to parse JSON ({parse_err.__class__.__name__}). Attempting rescue...")
                
                # Attempt A: maybe the raw content string itself has a content key we can pull
                rescued_content = self._rescue_content_field(response_content)
                if rescued_content:
                    logger.info(f"Rescued content field from partial JSON.")
                    return AgentOutput(type="response", content=rescued_content)
                
                # Attempt B: strip any JSON-looking text so we never speak raw JSON to the user
                safe_text = self._strip_json_text(response_content)
                if safe_text:
                    return AgentOutput(type="response", content=safe_text)
                
                # Last resort
                return AgentOutput(
                    type="response",
                    content="I encountered an issue processing my response. Please try again."
                )
                
        except Exception as e:
            # Fallback for API errors or critical failures
            print(f"[LLM Error] {e}")
            return AgentOutput(
                type="response", 
                content="I'm sorry, I encountered an internal error while processing your request."
            )

    def _extract_json(self, content: str) -> str:
        """
        Extracts the first valid JSON object from a string using brace-counting
        to correctly handle nested objects.
        Handles markdown code blocks and conversational text wrapping.
        """
        content = content.strip()
        
        # 1. Try to find JSON within markdown code blocks first
        code_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(code_block_pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # 2. Brace-counting: find the outermost { ... } correctly
        start = content.find('{')
        if start == -1:
            return content  # no JSON at all
        
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(content[start:], start=start):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return content[start: i + 1]
        
        # 3. Fallback: Return original content if no complete JSON found
        return content

    def _rescue_content_field(self, raw: str) -> str:
        """
        Attempts to extract just the 'content' string value from a JSON blob
        when full parse fails, using a targeted regex.
        Returns empty string if nothing usable is found.
        """
        # Match: "content": "..."
        match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        if match:
            # Unescape common JSON escape sequences
            text = match.group(1)
            text = text.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
            return text.strip()
        return ""

    def _strip_json_text(self, raw: str) -> str:
        """
        Removes JSON-looking blocks from a string so the remainder can be spoken.
        Used as a last-resort fallback before returning an error message.
        """
        # Remove markdown code fences
        cleaned = re.sub(r"```(?:json)?.*?```", "", raw, flags=re.DOTALL).strip()
        # Remove bare JSON objects { ... }
        cleaned = re.sub(r"\{[^{}]*\}", "", cleaned).strip()
        # Collapse extra whitespace
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned if len(cleaned) > 5 else ""

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        lc_msgs = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                lc_msgs.append(SystemMessage(content=content))
            elif role == "user":
                lc_msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_msgs.append(AIMessage(content=content))
            elif role == "tool":
                lc_msgs.append(HumanMessage(content=f"Tool Result: {content}"))
        return lc_msgs
