import os
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder

# =========================
# Config
# =========================

# Your Azure AI Foundry project endpoint
# (From Project Overview in Azure AI Foundry)
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://companyresearch.services.ai.azure.com/api/projects/companyResearch",
)

# Your existing agent ID (asst_...)
AGENT_ID = os.environ.get("AGENT_ID", "asst_Wb2ElHzBXdZtjCIOXlwoE8a3")

if not PROJECT_ENDPOINT:
    raise RuntimeError("PROJECT_ENDPOINT is not set.")
if not AGENT_ID:
    raise RuntimeError("AGENT_ID is not set.")

# Create a single shared client using DefaultAzureCredential
# Make sure your identity has access to the AI project.
project = AIProjectClient(
    credential=DefaultAzureCredential(),
    endpoint=PROJECT_ENDPOINT,
)

app = FastAPI()

# =========================
# Simple HTML UI
# =========================

HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Leadership Change Assistant</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 16px 40px;
      background: #fafafa;
    }
    h1 {
      font-size: 26px;
      margin-bottom: 4px;
    }
    .subtitle {
      color: #666;
      margin-bottom: 20px;
      font-size: 14px;
    }
    form {
      background: #ffffff;
      padding: 16px;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.03);
      margin-bottom: 16px;
    }
    textarea {
      width: 100%;
      min-height: 90px;
      padding: 10px;
      font-family: inherit;
      font-size: 14px;
      border-radius: 8px;
      border: 1px solid #ddd;
      box-sizing: border-box;
      resize: vertical;
    }
    button {
      margin-top: 10px;
      padding: 8px 18px;
      cursor: pointer;
      border-radius: 999px;
      border: none;
      font-size: 14px;
      background: #111827;
      color: #fff;
    }
    button:hover {
      background: #111827ee;
    }
    .answer {
      margin-top: 12px;
      padding: 14px;
      border-radius: 12px;
      background: #f3f4f6;
      white-space: pre-wrap;
      font-size: 14px;
      line-height: 1.5;
    }
    .label {
      font-weight: 600;
      margin-bottom: 6px;
      display:block;
      font-size: 14px;
    }
    .hint {
      font-size: 12px;
      color: #888;
      margin-top: 4px;
    }
  </style>
</head>
<body>
  <h1>Leadership Change Assistant</h1>
  <div class="subtitle">
    Query executive & director leadership changes (e.g. 8-K Item 5.02 events) across tracked companies.
    Try: <code>Show me leadership changes for Apple in 2025.</code>
  </div>

  <form method="post" action="/chat">
    <label for="message" class="label">Your question</label>
    <textarea id="message" name="message" required>{{message}}</textarea>
    <div class="hint">
      The agent will search recent filings and summarize relevant leadership moves.
    </div>
    <button type="submit">Ask</button>
  </form>

  {{answer_block}}
</body>
</html>
"""

def render(message: str = "", answer: str = "") -> HTMLResponse:
    """Render the HTML page with optional answer."""
    if answer:
        safe_answer = (
            answer.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
        )
        answer_block = (
            '<div class="answer">'
            '<strong>Answer</strong><br/>'
            f'{safe_answer}'
            '</div>'
        )
    else:
        answer_block = ""

    safe_message = (
        (message or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    html = (
        HTML
        .replace("{{message}}", safe_message)
        .replace("{{answer_block}}", answer_block)
    )
    return HTMLResponse(content=html)


# =========================
# Agent Call
# =========================

def call_agent(user_message: str) -> str:
    try:
        # 1) Verify agent exists (optional but nice; cached on first call)
        agent = project.agents.get_agent(AGENT_ID)

        # 2) Create thread
        thread = project.agents.threads.create()

        # 3) Add user message
        project.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message,
        )

        # 4) Run agent and process to completion
        run = project.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
        )

        if run.status == "failed":
            return f"Run failed: {run.last_error}"

        # 5) Collect assistant messages, ascending order
        messages = project.agents.messages.list(
            thread_id=thread.id,
            order=ListSortOrder.ASCENDING,
        )

        answers = []
        for msg in messages:
            if msg.role == "assistant" and getattr(msg, "text_messages", None):
                # grab latest text chunk in that message
                answers.append(msg.text_messages[-1].text.value)

        if not answers:
            return "(No assistant reply found.)"

        return "\n\n".join(answers).strip()

    except Exception as e:
        # Surface a compact error instead of full stack trace in the UI
        return f"Error calling agent: {e}"


# =========================
# Routes
# =========================

@app.get("/", response_class=HTMLResponse)
async def index():
    return render()


@app.post("/chat", response_class=HTMLResponse)
async def chat(message: str = Form(...)):
    answer = call_agent(message)
    return render(message=message, answer=answer)
