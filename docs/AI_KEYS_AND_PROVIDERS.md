# 🧠 AI Providers & API Keys Setup Guide

**Garmin AI Coach** features a flexible AI engine. You can choose between **Google Gemini** (free, fast, and recommended) or any **OpenAI-compatible provider** (OpenAI, Groq, OpenRouter, or a self-hosted local Ollama instance).

---

## 🗺️ Supported Providers Overview

```mermaid
flowchart TD
    PromptEngine["Sport-Specific Prompt Engine"] --> Router{"AI_PROVIDER setting"}

    Router -->|gemini (Default)| Gemini["Google Gemini API\n• gemini-2.5-flash\n• Auto-fallback to 1.5-flash"]
    Router -->|openai| OpenAICompat["OpenAI-Compatible Endpoint (/chat/completions)"]

    OpenAICompat --> OAI["OpenAI (gpt-4o-mini, gpt-4o)"]
    OpenAICompat --> Groq["Groq Cloud (Llama 3.3 70B - Ultra Fast)"]
    OpenAICompat --> OR["OpenRouter (Claude 3.5 Sonnet, DeepSeek)"]
    OpenAICompat --> Ollama["Local Ollama (100% Offline & Private)"]
```

---

## 1. Option 1: Google Gemini (Recommended & Free Tier)

Google Gemini is the default provider because it offers a generous free tier (no credit card required), sub-second inference speeds, and an immense context window capable of analyzing months of continuous health history.

### How to Get Your Gemini API Key:
1. Navigate to **[Google AI Studio](https://aistudio.google.com/)**.
2. Sign in with your standard Google account.
3. Click the blue **"Get API key"** button in the left sidebar.
4. Click **"Create API key in new project"** (or choose an existing GCP project).
5. Copy your generated key (starts with `AIzaSy...`).
6. Add it to your `.env` file:
   ```dotenv
   AI_PROVIDER=gemini
   GEMINI_API_KEY=AIzaSyD...your_real_gemini_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

### Recommended Models:
| Model | Strengths | Free Quota |
| :--- | :--- | :--- |
| `gemini-2.5-flash` *(Default)* | Best balance of speed, athletic reasoning, and stability. | 15 RPM / 1M TPM |
| `gemini-1.5-flash` | Ultra-light, resilient fallback model. | 15 RPM / 1M TPM |
| `gemini-2.0-flash` | Next-generation multimodal architecture. | Fast response |
| `gemini-1.5-pro` | Deep physiological reasoning for seasonal training plans. | 2 RPM |

> [!TIP]
> **Resilient Model Fallback:** If `gemini-2.5-flash` ever reaches temporary rate limits, the system automatically falls back to `gemini-1.5-flash` without interrupting your morning or workout notifications!

---

## 2. Option 2: OpenAI (ChatGPT)

If you have an OpenAI account and want to use GPT-4o:

1. Visit **[OpenAI API Keys](https://platform.openai.com/api-keys)**.
2. Click **"Create new secret key"** and copy the key (`sk-...`).
3. In your `.env` file:
   ```dotenv
   AI_PROVIDER=openai
   OPENAI_API_KEY=sk-...your_openai_key
   OPENAI_BASE_URL=https://api.openai.com/v1
   OPENAI_MODEL=gpt-4o-mini
   ```

---

## 3. Option 3: Groq Cloud (Free & Ultra-Fast)

Groq offers ultra-fast inference with popular open-weights models like Llama 3.3 70B:

1. Sign up at **[Groq Console](https://console.groq.com/keys)**.
2. Create an API key (`gsk_...`).
3. Configure your `.env`:
   ```dotenv
   AI_PROVIDER=openai
   OPENAI_API_KEY=gsk_...your_groq_key
   OPENAI_BASE_URL=https://api.groq.com/openai/v1
   OPENAI_MODEL=llama-3.3-70b-versatile
   ```

---

## 4. Option 4: Local Ollama (100% Offline & Private)

If you prefer complete data privacy where zero health biometrics leave your home network:

1. Install **[Ollama](https://ollama.com/)** on your machine or homelab server.
2. Pull a sports-reasoning model:
   ```bash
   ollama run llama3.1
   # or
   ollama run qwen2.5:14b
   ```
3. Set your `.env` to point to your local Ollama port (`11434`):
   ```dotenv
   AI_PROVIDER=openai
   OPENAI_API_KEY=ollama
   OPENAI_BASE_URL=http://localhost:11434/v1
   OPENAI_MODEL=llama3.1
   ```

---

## 5. Option 5: OpenRouter (Multi-Model Hub)

To route requests through Claude 3.5 Sonnet, DeepSeek V3, or Mistral:

1. Get a key at **[OpenRouter.ai](https://openrouter.ai/keys)**.
2. Configure your `.env`:
   ```dotenv
   AI_PROVIDER=openai
   OPENAI_API_KEY=sk-or-v1-...
   OPENAI_BASE_URL=https://openrouter.ai/api/v1
   OPENAI_MODEL=anthropic/claude-3.5-sonnet
   ```
