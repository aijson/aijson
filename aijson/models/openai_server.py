from pydantic import BaseModel


class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIChatCompletionRequest(BaseModel):
    messages: list[OpenAIMessage]
    model: None | str = None
    max_tokens: None | int = None
    temperature: None | float = None
    stream: None | bool = None
