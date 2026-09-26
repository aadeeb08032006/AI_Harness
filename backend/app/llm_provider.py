import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from openai import OpenAI


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


class AnthropicProvider(LLMProvider):

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key is None:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))

    def generate(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)
        except anthropic.APIError as e:
            return LLMResponse(
                text=None,
                tool_calls=[],
                stop_reason="error",
                raw={"error": str(e)},
            )

        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    def format_tool_result(
        self, tool_call_id: str, content: str, is_error: bool = False
    ) -> dict:
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content,
                "is_error": is_error,
            }],
        }

    def format_assistant_message(self, response: LLMResponse) -> dict:
        content = []
        if response.text is not None:
            content.append({
                "type": "text",
                "text": response.text,
            })

        for tc in response.tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"],
            })

        return {
            "role": "assistant",
            "content": content,
        }


class OpenAICompatibleProvider(LLMProvider):

    def __init__(self):
        api_key = os.environ.get("LLM_API_KEY")
        if api_key is None:
            raise ValueError("LLM_API_KEY not set")
        base_url = os.environ.get("LLM_BASE_URL")
        # DeepSeek: https://api.deepseek.com
        # Qwen (DashScope): https://dashscope.aliyuncs.com/compatible-mode/v1
        if base_url is None:
            raise ValueError("LLM_BASE_URL not set")
        self.model = os.environ.get("LLM_MODEL")
        # e.g. "deepseek-chat" or "qwen-max" — must match provider's exact model string
        if self.model is None:
            raise ValueError("LLM_MODEL not set")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

    def generate(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        chat_messages = list(messages)
        if system is not None:
            chat_messages.insert(0, {"role": "system", "content": system})

        kwargs = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": self.max_tokens,
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
        msg = {
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


def format_tool_result(tool_call_id: str, content: str, is_error: bool = False) -> dict:
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": content,
            "is_error": is_error,
        }],
    }


def format_assistant_message(response: LLMResponse) -> dict:
    content = []
    if response.text is not None:
        content.append({
            "type": "text",
            "text": response.text,
        })

    for tc in response.tool_calls:
        content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["name"],
            "input": tc["input"],
        })

    return {
        "role": "assistant",
        "content": content,
    }


def get_provider() -> LLMProvider:
    provider_name = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider_name == "anthropic":
        return AnthropicProvider()
    elif provider_name in ("openai", "deepseek", "qwen"):
        return OpenAICompatibleProvider()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name}")
