import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI, RateLimitError

from core.models import EvaluationVerdict, TargetAgentProfile, ToolDefinition

load_dotenv()

logger = logging.getLogger("redteam_client")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [Client]: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "qwen/qwen3.8-27b",
        timeout: float = 45.0
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("No API key provided or found in environment variables.")
            raise ValueError("API Key is missing. Set GROQ_API_KEY or OPENAI_API_KEY.")

        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.model = model
        self.timeout = timeout

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            logger.info(f"Initialized LLMClient for model '{self.model}' via endpoint '{self.base_url}'.")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            raise

    def sanitize_json_response(self, text: str) -> Dict[str, Any]:
        cleaned = re.sub(r"^```[a-zA-Z]*\n", "", text.strip())
        cleaned = re.sub(r"\n```$", "", cleaned)

        json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed on text: '{text[:200]}...' Error: {e}")
            raise ValueError(f"Unable to parse valid JSON from model response: {e}") from e

    def extract_probe_payload(self, text: str) -> str:
        probe_match = re.search(r"<probe>(.*?)</probe>", text, re.DOTALL)
        if probe_match:
            return probe_match.group(1).strip()

        cleaned = text.strip()
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()

        logger.debug("No <probe> tags found. Using sanitized raw response.")
        return cleaned

    def query(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7
    ) -> Tuple[str, List[Dict[str, Any]]]:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            content = message.content or ""

            tool_calls_extracted = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {"raw_arguments": tc.function.arguments}

                    tool_calls_extracted.append({
                        "name": tc.function.name,
                        "arguments": args
                    })

            return content, tool_calls_extracted

        except RateLimitError as e:
            logger.error(f"API Rate limit hit: {e}")
            raise
        except AuthenticationError as e:
            logger.error(f"API Authentication failed: {e}")
            raise
        except APIConnectionError as e:
            logger.error(f"Failed to connect to API endpoint: {e}")
            raise
        except APIError as e:
            if tools and "tools" in str(e).lower():
                logger.warning("Target endpoint rejected native 'tools' parameter. Attempting fallback.")
                return self._fallback_tool_query(messages, tools, temperature)
            logger.error(f"API returned an error: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during completion call: {e}", exc_info=True)
            raise

    def _fallback_tool_query(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float
    ) -> Tuple[str, List[Dict[str, Any]]]:
        tool_descriptions = json.dumps(tools, indent=2)
        fallback_instruction = (
            "\n\n[AVAILABLE TOOLS SCHEMA]\n"
            "If you decide to invoke a tool, output your decision in this exact format:\n"
            "TOOL_CALL: {\"name\": \"tool_name\", \"arguments\": {\"param\": \"value\"}}\n"
            f"{tool_descriptions}"
        )

        adapted_messages = list(messages)
        if adapted_messages and adapted_messages[0]["role"] == "system":
            adapted_messages[0] = {
                "role": "system",
                "content": adapted_messages[0]["content"] + fallback_instruction
            }

        response = self.client.chat.completions.create(
            model=self.model,
            messages=adapted_messages,
            temperature=temperature
        )
        content = response.choices[0].message.content or ""

        tool_calls = []
        pattern = r"TOOL_CALL:\s*(\{.*?\})"
        matches = re.findall(pattern, content, re.DOTALL)
        for m in matches:
            try:
                parsed = json.loads(m)
                tool_calls.append({
                    "name": parsed.get("name", "unknown"),
                    "arguments": parsed.get("arguments", {})
                })
            except json.JSONDecodeError:
                continue

        return content, tool_calls