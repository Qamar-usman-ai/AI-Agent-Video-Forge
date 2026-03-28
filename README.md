# 🤖 AI Agent Video Forge (Advanced Edition)

The **AI Agent Video Forge** is an intelligent video production pipeline that uses **Llama-3.1-8b-instant** as an automated Director. Instead of manual configuration, the agent interprets user prompts to write scripts, select voices (Urdu or English), and manage audio-visual synchronization.

---

## 🧠 How the Agent Works

1.  **Instruction Analysis:** The Llama 3.1 model parses your natural language input (e.g., *"Make a short Urdu clip about hard work with an aggressive tone"*).
2.  **Strategic Planning:** The agent generates a JSON "Production Plan" containing:
    * A custom-written script in the correct language.
    * The most appropriate AI Voice ID (from `edge-tts`).
    * Audio parameters (Pitch, Rate, and Background Volume).
3.  **Automated Assembly:** The Python backend executes the plan, stretching or compressing video clips to match the generated speech perfectly.

---

## 🛠️ Technical Stack

* **LLM:** Llama-3.1-8b-instant (via Groq)
* **Voice Synth:** Edge-TTS (Microsoft Neural Voices)
* **Video Engine:** MoviePy 2.0.0+
* **Interface:** Streamlit
* **Orchestration:** Asyncio

---

## ⚙️ Setup & Installation

### 1. Prerequisites
* Python 3.12+
* FFmpeg (Required for MoviePy)
* A **Groq API Key** (Get it free at [console.groq.com](https://console.groq.com/))

### 2. Environment Configuration
Create a `.env` file or add to your **Streamlit Secrets**:
```text
GROQ_API_KEY=your_actual_api_key_here
