# Provider Contracts

## LLMProvider Protocol
- async invoke(messages) -> AIMessage
- DeepSeekProvider implements Anthropic-compatible Messages API

## ProviderTransport (Injectable)
- async post(url, headers, body, timeout) -> (status, body)
- FakeHTTPTransport for deterministic tests

## Authentication
- Token from DEEPSEEK_API_TOKEN environment variable
- Never stored in source or config files
- Credential redaction in logs and stored request traces
