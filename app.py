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
TITLE_PROMPT = (
    "You name chats. You get the first user message inside <message> tags. "
    "Do NOT answer it. Reply only with a short chat title (2-5 words) "
    "in the SAME language as the message (Ukrainian or English). "
    "No quotes, no final period, no formatting."
)
INDEX_HTML = Path(__file__).parent / "static" / "index.html"

client = Groq()
db.init_db()  # створюємо таблиці (і переносимо стару історію) при старті сервера

app = FastAPI()


class ChatRequest(BaseModel):
    message: str


def get_chat_or_404(chat_id):
    chat = db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Чат не знайдено")
    return chat


def generate_title(first_message):
    """Окремий короткий запит: NUYRA придумує назву за першим повідомленням."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": TITLE_PROMPT},
            {"role": "user", "content": f"<message>{first_message}</message>"},
        ],
    )
    # беремо лише перший рядок і знімаємо лапки та Markdown-зірочки
    title = (response.choices[0].message.content.strip().splitlines() or [""])[0]
    title = title.strip("\"«»*# ")
    return title[:60] or db.NEW_CHAT_TITLE


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)  # віддаємо сторінку чату


@app.get("/chats")
def list_chats():
    return db.list_chats()  # список для бічної панелі


@app.post("/chats", status_code=201)
def create_chat():
    return db.create_chat()


@app.delete("/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: int):
    if not db.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Чат не знайдено")


@app.get("/chats/{chat_id}/messages")
def chat_messages(chat_id: int):
    get_chat_or_404(chat_id)
    return db.get_messages(chat_id)


@app.post("/chats/{chat_id}/messages")
def send_message(chat_id: int, req: ChatRequest):
    chat = get_chat_or_404(chat_id)
    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Повідомлення порожнє")

    # модель нічого не пам'ятає, тому щоразу надсилаємо всю історію чату
    previous = db.get_messages(chat_id)
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    history += previous
    history.append({"role": "user", "content": text})

    try:
        response = client.chat.completions.create(model=MODEL, messages=history)
    except APIError:
        raise HTTPException(status_code=502, detail="Groq не відповів, спробуй ще раз")

    answer = response.choices[0].message.content
    db.add_message(chat_id, "user", text)       # зберігаємо обидва повідомлення
    db.add_message(chat_id, "assistant", answer)  # лише коли відповідь успішна

    title = chat["title"]
    if not previous:  # це перше повідомлення в чаті — час придумати назву
        try:
            title = generate_title(text)
            db.rename_chat(chat_id, title)
        except APIError:
            pass  # назва не критична: якщо не вийшло, лишається «Новий чат»

    return {"answer": answer, "title": title}
