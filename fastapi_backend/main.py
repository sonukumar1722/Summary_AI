# main.py

import os
import httpx
import markdown
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List
from dotenv import load_dotenv

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# --- New Imports for Email ---
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig



# Load environment variables from a .env file
load_dotenv()
# --- Pydantic Models for Data Validation ---
class SummaryRequest(BaseModel):
    transcript: str
    prompt: str

class SummaryResponse(BaseModel):
    summary_html: str
    summary_markdown: str # Also send raw markdown for editing

class EmailRequest(BaseModel):
    recipients: List[EmailStr]
    content: str # The edited summary content (HTML or plain text)

# --- FastAPI App Initialization ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Email Configuration ---
conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD'),
    MAIL_FROM = os.getenv('MAIL_FROM'),
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587)),
    MAIL_SERVER = os.getenv('MAIL_SERVER'),
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

# --- Serve Frontend ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

# Serve index.html at /

@app.get("/")
async def serve_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.isfile(index_path):
        # Helpful error if Render root misconfigured
        return {"error": "index.html not found. Ensure Render root includes /frontend."}
    return FileResponse(index_path)

# --- API Endpoints ---
@app.post("/api/generate-summary", response_model=SummaryResponse)
async def generate_summary(request_data: SummaryRequest):
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="Server is not configured with an API key.")

    headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://summary-app-backend.onrender.com"
}

    json_payload = {
        "model": "mistral-7b-instruct",

        "messages": [
            {"role": "system", "content": "You are an expert assistant who creates structured summaries from transcripts. Your response must be in Markdown format."},
            {"role": "user", "content": f'Instruction: "{request_data.prompt}".\n\nTranscript: "{request_data.transcript}"'}
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            print('generate_summary called')
            response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_payload, timeout=60.0)
            print(response)
            response.raise_for_status()
            api_data = response.json()
            markdown_summary = api_data['choices'][0]['message']['content']
            html_summary = markdown.markdown(markdown_summary)
            return SummaryResponse(summary_html=html_summary, summary_markdown=markdown_summary)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/share-email")
async def share_email(email_data: EmailRequest):
    if not all([conf.MAIL_USERNAME, conf.MAIL_PASSWORD, conf.MAIL_SERVER]):
         raise HTTPException(status_code=500, detail="Email service is not configured on the server.")

    message = MessageSchema(
        subject="AI-Generated Summary",
        recipients=email_data.recipients,
        body=f"Here is the summary you requested:\n\n{email_data.content}",
        subtype="plain"
    )
    try:
        fm = FastMail(conf)
        await fm.send_message(message)
        return {"message": "Email sent successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")
