import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import anthropic

@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: Optional[str] = None
    raw: Optional[dict] = None

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[dict], system: Optional[str] = None,
                 tools: Optional[list[dict]] = None) -> LLMResponse: ...

class AnthropicProvider(LLMProvider):

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key is None:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_tokens = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))

    def generate(self, messages: list[dict], system: Optional[str] = None, tools: Optional[list[dict]] = None) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages
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
                raw={"error": str(e)}
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
                    "input": block.input
                })

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw=response.model_dump() if hasattr(response, "model_dump") else None
        )

def format_tool_result(tool_call_id: str, content: str, is_error: bool = False) -> dict:
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": content,
            "is_error": is_error
        }]
    }

def format_assistant_message(response: LLMResponse) -> dict:
    content = []
    if response.text is not None:
        content.append({
            "type": "text",
            "text": response.text
        })
    
    for tc in response.tool_calls:
        content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["name"],
            "input": tc["input"]
        })

    return {
        "role": "assistant",
        "content": content
    }
