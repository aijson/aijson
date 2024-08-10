from typing import Optional, Literal, Annotated

from pydantic import Field

from aijson.models.config.common import StrictModel

ModelType = (
    # ollama models
    Annotated[
        Literal[
            "ollama/llama3",
            "ollama/llama3:8b",
            "ollama/llama3:70b",
            "ollama/gemma",
            "ollama/gemma:2b",
            "ollama/gemma:7b",
            "ollama/mixtral",
            "ollama/mixtral:8x7b",
            "ollama/mixtral:8x22b",
        ],
        Field(
            description="Run inference on [Ollama](https://ollama.com/); defaults `api_base` to `localhost:11434`"
        ),
    ]
    |
    # openai models
    Annotated[
        Literal[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-1106-preview",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo-16k",
            "gpt-3.5-turbo-1106",
            "gpt-3.5-turbo",
        ],
        Field(
            description="OpenAI model; requires `OPENAI_API_KEY` environment variable"
        ),
    ]
    |
    # google models
    Annotated[
        Literal["gemini-pro",],
        Field(
            description="Google model; requires `GCP_CREDENTIALS_64` environment variable (base64-encoded GCP credentials JSON)"
        ),
    ]
    |
    # anthropic models
    Annotated[
        Literal[
            "claude-3-5-sonnet-20240620",
            "claude-3-haiku-20240307",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
        ],
        Field(
            description="Anthropic model; requires `ANTHROPIC_API_KEY` environment variable"
        ),
    ]
    |
    # bedrock models
    Annotated[
        Literal[
            "bedrock/ai21.j2-mid-v1",
            "bedrock/ai21.j2-ultra-v1",
            "bedrock/amazon.titan-text-express-v1",
            "bedrock/amazon.titan-text-lite-v1",
            "bedrock/amazon.titan-text-premier-v1:0",
            # "bedrock/amazon.titan-embed-text-v1",
            # "bedrock/amazon.titan-embed-text-v2:0",
            # "bedrock/amazon.titan-embed-image-v1",
            # "bedrock/amazon.titan-image-generator-v1",
            # "bedrock/amazon.titan-image-generator-v2:0",
            "bedrock/anthropic.claude-v2",
            "bedrock/anthropic.claude-v2:1",
            "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
            "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
            "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
            "bedrock/anthropic.claude-3-opus-20240229-v1:0",
            "bedrock/anthropic.claude-instant-v1",
            "bedrock/cohere.command-text-v14",
            "bedrock/cohere.command-light-text-v14",
            "bedrock/cohere.command-r-v1:0",
            "bedrock/cohere.command-r-plus-v1:0",
            # "bedrock/cohere.embed-english-v3",
            # "bedrock/cohere.embed-multilingual-v3",
            "bedrock/meta.llama2-13b-chat-v1",
            "bedrock/meta.llama2-70b-chat-v1",
            "bedrock/meta.llama3-8b-instruct-v1:0",
            "bedrock/meta.llama3-70b-instruct-v1:0",
            "bedrock/meta.llama3-1-8b-instruct-v1:0",
            "bedrock/meta.llama3-1-70b-instruct-v1:0",
            "bedrock/meta.llama3-1-405b-instruct-v1:0",
            "bedrock/mistral.mistral-7b-instruct-v0:2",
            "bedrock/mistral.mixtral-8x7b-instruct-v0:1",
            "bedrock/mistral.mistral-large-2402-v1:0",
            "bedrock/mistral.mistral-large-2407-v1:0",
            "bedrock/mistral.mistral-small-2402-v1:0",
            # "bedrock/stability.stable-diffusion-xl-v0",
            # "bedrock/stability.stable-diffusion-xl-v1",
        ],
        Field(
            description="Bedrock model; requires `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables"
        ),
    ]
    | str
)


BiEncoderModelType = Literal[
    "sentence-transformers/all-mpnet-base-v2",
    "BAAI/bge-small-en-v1.5",
]
CrossEncoderModelType = Literal[
    "cross-encoder/ms-marco-TinyBERT-L-2-v2",
    "BAAI/bge-reranker-base",
]


class ModelConfig(StrictModel):
    max_output_tokens: int = 2000
    max_prompt_tokens: int = 8000
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    model: ModelType
    api_base: Optional[str] = None
    auth_token: Optional[str] = None


class OptionalModelConfig(ModelConfig):
    max_output_tokens: Optional[int] = None
    max_prompt_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    model: Optional[ModelType] = None
    api_base: Optional[str] = None
    auth_token: Optional[str] = None
