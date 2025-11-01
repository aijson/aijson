<div align="center">

<a href="https://aijson.com">
  <img src="https://github.com/user-attachments/assets/85ed4004-92d3-4e68-a6f1-1198e0474db6" width="200" />
</a>

<h1>AI JSON / AI YAML</h1>

[![discord](https://img.shields.io/badge/discord-7289da)](https://discord.gg/8rVxacHn9H)
[![docs](https://img.shields.io/badge/docs-orange)](https://aijson.com/docs)

**Build AI pipelines with YAML configuration files**

A declarative, low-code framework for composing complex AI workflows using YAML. Connect LLMs, process documents, perform retrieval, and orchestrate multi-step AI tasks without writing boilerplate code.

</div>

[demo.webm](https://github.com/user-attachments/assets/a20fedab-30e6-4459-9fe5-5c5a21a52c9f)

## What is AI JSON?

AI JSON (package: `aijson-core`) is a Python framework that lets you build production-ready AI applications using simple YAML configuration files. Define your AI workflows declaratively, and the framework handles execution, caching, error handling, and orchestration.

**Write this:**
```yaml
version: "0.1"
flow:
  summarize:
    action: llm
    prompt: "Summarize this text: {{ input_text }}"
    model: gpt-4
```

**Instead of this:**
```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": f"Summarize this text: {input_text}"}]
)
# + error handling, retries, caching, logging...
```

## Key Features

- **🔌 Multi-LLM Support** - Unified interface for OpenAI, Anthropic, Google, Ollama, AWS Bedrock, and 100+ providers via LiteLLM
- **🧩 Built-in Actions** - LLM calls, PDF extraction, list parsing, XML extraction, vector search, reranking, and more
- **🔄 Advanced Workflows** - Loops, conditionals, variable references, Jinja2 templating, and lambda expressions
- **⚡ Production Ready** - Built-in caching (Redis/Shelve), async execution, streaming, and retry logic
- **🚀 API Server** - Serve flows as OpenAI-compatible chat completion endpoints
- **🎨 Web UI** - Built-in Gradio interface for testing and previewing flows
- **🔧 Extensible** - Register custom actions with the `@register_action` decorator

## Installation

```bash
pip install aijson-core
```

**With optional dependencies:**
```bash
# For OpenAI support
pip install aijson-core[openai]

# For Anthropic support
pip install aijson-core[anthropic]

# For PDF processing
pip install aijson-core[pdf]

# For vector search and embeddings
pip install aijson-core[transformers]

# For database support
pip install aijson-core[pg]      # PostgreSQL
pip install aijson-core[sqlite]  # SQLite

# Install multiple extras
pip install aijson-core[openai,anthropic,pdf,transformers]
```

## Quick Start

1. **Create a flow file** (`hello_world.ai.yaml`):
```yaml
version: "0.1"
flow:
  hello_world:
    action: llm
    prompt:
      - text: Can you say hello world for me?
```

2. **Run it with Python:**
```python
from aijson import Flow

flow = Flow.from_file("hello_world.ai.yaml")
result = await flow.run()
print(result)  # "Hello World!"
```

3. **Or use the CLI:**
```bash
# Test with Gradio UI
python -m aijson.scripts.gradio_ui hello_world.ai.yaml

# Serve as OpenAI-compatible API
python -m aijson.scripts.openai_server hello_world.ai.yaml
```

## Example: RAG Chatbot

Here's a real-world example from `examples/chatbot.ai.yaml` that implements a Retrieval-Augmented Generation (RAG) system:

```yaml
version: "0.1"
flow:
  # Extract text from PDFs
  extract_pdf_texts:
    for: filepath
    in:
      var: pdf_filepaths
    flow:
      extractor:
        action: extract_pdf_text
        file:
          var: filepath

  # Generate search query from user message
  generate_query:
    action: llm
    prompt:
      - heading: User's Message
        var: message
      - text: |
          Analyze the user's message and generate a clear query
          for vector search. Put it in <query></query> tags.

  extract_query:
    action: extract_xml_tag
    tag: query
    text:
      link: generate_query.result

  # Vector search through documents
  retrieval:
    action: retrieve
    k: 20
    documents:
      lambda: |
        [page for flow in extract_pdf_texts
         for page in flow.extractor.pages]
    query:
      link: extract_query.result

  # Rerank for best matches
  reranking:
    action: rerank
    k: 5
    documents:
      link: retrieval.result
    query:
      link: extract_query.result

  # Generate response with context
  chatbot:
    action: llm
    prompt:
      - role: system
      - text: You are an expert analyst.
      - heading: Relevant Pages
        text: |
          {% for page in reranking.result -%}
            {{ page.title }} - {{ page.text }}
          {% endfor %}
      - heading: User Message
        var: message
```

**Run it:**
```python
flow = Flow.from_file("chatbot.ai.yaml")
flow.set_vars(
    pdf_filepaths=["document1.pdf", "document2.pdf"],
    message="What are the key findings?"
)
result = await flow.run()
```

## Core Concepts

### Actions
Actions are the building blocks of flows. Built-in actions include:
- `llm` - Call language models with templated prompts
- `extract_pdf_text` - Extract text from PDFs
- `extract_list` - Parse lists from text
- `extract_xml_tag` - Extract XML tags
- `retrieve` - Vector search for semantic retrieval
- `rerank` - Rerank documents by relevance

### Value Declarations
Reference variables, link to previous outputs, or use lambda expressions:
```yaml
flow:
  step1:
    action: llm
    prompt:
      var: user_input          # Reference a variable

  step2:
    action: llm
    prompt:
      link: step1.result       # Link to previous output

  step3:
    action: some_action
    items:
      lambda: |                # Lambda expression
        [x.upper() for x in step1.result]
```

### Loops
Process collections with `for...in` loops:
```yaml
process_items:
  for: item
  in:
    var: items_list
  flow:
    analyze:
      action: llm
      prompt: "Analyze: {{ item }}"
```

### Templating
Use Jinja2 templates in prompts and text fields:
```yaml
summarize:
  action: llm
  prompt: |
    {% for doc in documents -%}
      Document {{ loop.index }}: {{ doc }}
    {% endfor %}
    Summarize the above documents.
```

## Production Features

### Caching
Configure caching with Redis or Shelve:
```python
from aijson import Flow
from aijson.repos.cache.redis_repo import RedisCacheRepo

cache = RedisCacheRepo(host="localhost", port=6379)
flow = Flow.from_file("flow.ai.yaml", cache_repo=cache)
```

### Streaming
Stream results in real-time:
```python
async for chunk in flow.stream():
    print(chunk, end="", flush=True)
```

### Error Handling
Built-in retry logic via Tenacity for robust execution.

### API Server
Serve flows as OpenAI-compatible endpoints:
```bash
python -m aijson.scripts.openai_server chatbot.ai.yaml --port 8000
```

Then use with any OpenAI-compatible client:
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1")

response = client.chat.completions.create(
    model="chatbot",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Examples

Check out the `examples/` directory for more:
- `hello_world.ai.yaml` - Simple LLM call
- `chatbot.ai.yaml` - Full RAG system with PDF extraction and vector search
- `application_judgement.ai.yaml` - Multi-step evaluation with scoring
- `debono.ai.yaml` - Six Thinking Hats problem-solving framework
- `text_style_transfer.ai.yaml` - Style-based text generation
- `meeting_review.ai.yaml` - Meeting notes analysis

## Documentation

Full documentation available at [aijson.com/docs](https://aijson.com/docs)

## Community

- **Discord**: [Join our community](https://discord.gg/8rVxacHn9H)
- **Website**: [aijson.com](https://aijson.com)

## Requirements

- Python 3.10-3.12
- See `pyproject.toml` for full dependency list

## License

MIT License - see LICENSE file for details
