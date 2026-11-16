from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from groq import APIError, Groq
from pydantic import BaseModel

import db

load_dotenv()  # читаємо GROQ_API_KEY з .env

MODEL = "openai/gpt-oss-120b"
SYSTEM_PROMPT = (
    "Ти NUYRA — помічник. Відповідай тією мовою, якою пише користувач: "
    "українською або англійською."
)
INDEX_HTML = Path(__file__).parent / "static" / "index.html"

client = Groq()
db.init_db()  # створюємо таблицю при старті сервера

app = FastAPI()


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)  # віддаємо сторінку чату


@app.get("/messages")
def messages():
    return db.get_messages()  # історія, щоб показати її після перезавантаження


@app.post("/chat")
def chat(req: ChatRequest):
    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Повідомлення порожнє")

    # модель нічого не пам'ятає, тому щоразу надсилаємо всю історію
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    history += db.get_messages()
    history.append({"role": "user", "content": text})

    try:
        response = client.chat.completions.create(model=MODEL, messages=history)
    except APIError:
        raise HTTPException(status_code=502, detail="Groq не відповів, спробуй ще раз")

    answer = response.choices[0].message.content
    db.add_message("user", text)       # зберігаємо обидва повідомлення
    db.add_message("assistant", answer)  # лише коли відповідь успішна
    return {"answer": answer}
