import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any

from groq import Groq


@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: Optional[str] = None
    raw: Optional[dict] = None


class LLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse: ...

    @abstractmethod
    def format_tool_result(
        self, tool_call_id: str, content: str, is_error: bool = False
    ) -> dict: ...

    @abstractmethod
    def format_assistant_message(self, response: LLMResponse) -> dict: ...


class GroqProvider(LLMProvider):

    def __init__(self):
        # Prefer the hackathon-standard AI_API_KEY, fallback to GROQ_API_KEY if needed.
        api_key = os.environ.get("AI_API_KEY") or os.environ.get("GROQ_API_KEY")
        if api_key is None:
            raise ValueError("AI_API_KEY not set")
        
        self.model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        self.client = Groq(api_key=api_key)
        self.max_tokens = int(os.environ.get("GROQ_MAX_TOKENS", "4096"))

    def generate(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        chat_messages = list(messages)
        if system is not None:
            chat_messages.insert(0, {"role": "system", "content": system})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.0,
        }

        if tools:
            converted_tools = []
            for t in tools:
                converted_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                })
            kwargs["tools"] = converted_tools

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            return LLMResponse(
                text=None,
                tool_calls=[],
                stop_reason="error",
                raw={"error": str(e)},
            )

        choice = response.choices[0]
        text = choice.message.content  # may be None if it's a pure tool call
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    try:
                        parsed_input = json.loads(arguments)
                    except Exception:
                        parsed_input = {"raw": arguments}
                else:
                    parsed_input = arguments

                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": parsed_input,
                })

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason,
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    def format_tool_result(
        self, tool_call_id: str, content: str, is_error: bool = False
    ) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": f"ERROR: {content}" if is_error else content,
        }

    def format_assistant_message(self, response: LLMResponse) -> dict:
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.text,
        }
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["input"])
                        if isinstance(tc["input"], (dict, list))
                        else str(tc["input"]),
                    },
                }
                for tc in response.tool_calls
            ]
        return msg


def get_provider() -> LLMProvider:
    return GroqProvider()
