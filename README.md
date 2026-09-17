# SecMate AI Red-Team Assessment

SecMate is a Streamlit demo for evaluating whether enterprise AI-agent personas resist prompt injection, data leakage, unsafe tool use, and policy-bypass attempts.

The project is intentionally self-contained: target personas and attack scenarios are defined in YAML, and generated audit reports are saved locally as JSON.

## Features

- Streamlit-based assessment dashboard.
- Multiple target personas under `configs/`.
- Attack scenario library in `attack_library.yaml`.
- OpenAI-compatible LLM client support for Groq, OpenAI, or compatible endpoints.
- Separate optional model roles for target, attacker, and judge.
- Deterministic tool-policy validation for risky tool calls.
- JSON report export into `reports/`.

## Project Structure

```text
.
├── app.py                    # Streamlit UI
├── attack_library.yaml       # Red-team scenario definitions
├── configs/                  # Target persona YAML files
├── core/                     # Client, engine, models, loader, policy validator
├── reports/                  # Local generated reports, ignored by git except .gitkeep
├── .env.example              # Environment variable template
├── requirements.txt          # Runtime Python dependencies
└── README.md
```

## Requirements

- Python 3.10 or newer is recommended.
- An API key for an OpenAI-compatible model provider.

The current default endpoint is Groq's OpenAI-compatible API:

```text
https://api.groq.com/openai/v1
```

## Setup

Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set your API key:

```text
GROQ_API_KEY=your_groq_api_key_here
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=qwen/qwen3.8-27b
ATTACKER_MODEL=qwen/qwen3.8-27b
JUDGE_MODEL=qwen/qwen3.8-27b
```

Do not commit `.env`.

## Run

```bash
streamlit run app.py
```

The app will open in your browser. Select a target persona, an attack scenario, assessment depth, and model settings, then run the assessment.

## Target Personas

The included target personas are defined in `configs/`:

- `SOCMate`: SOC triage and incident reporting assistant.
- `DBGuard-Bot`: read-only database investigation assistant.
- `IDShield-Bot`: identity and access operations assistant.
- `SOC/DB Agent`: legacy combined SOC/database persona.

Add new personas by creating additional `.yaml` files under `configs/` that match the existing schema.

## Attack Scenarios

Attack scenarios are defined in `attack_library.yaml`. Each scenario includes:

- ID
- name
- category
- severity
- description
- methodology recipe

The current scenarios cover authority override, context breakout, tool-argument injection, hypothetical framing, system prompt extraction, and obfuscation drift.

## Reports

Assessment reports are saved to `reports/` as JSON.

Generated report files are ignored by git to avoid committing local/client-specific assessment data.

## GitHub Hygiene

The repository is configured to ignore:

- `.env` and other local secret files.
- local virtual environments like `.venv/` and `venv/`.
- Python cache files like `__pycache__/` and `*.pyc`.
- generated JSON audit reports under `reports/`.

Before committing, verify what will be tracked:

```bash
git status
```

Expected files to commit include application code, YAML configs, `requirements.txt`, `.env.example`, `.gitignore`, and this README.

## Notes

- The project does not execute real SOC, database, or identity actions.
- Tools are represented as schemas and evaluated as simulated tool calls.
- This is intended as a red-team assessment demo and baseline framework, not a production incident-response system.
