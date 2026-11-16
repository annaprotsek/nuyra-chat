from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from groq import APIError, Groq
from pydantic import BaseModel

import db
from tools import TOOLS, run_tool

load_dotenv()  # читаємо GROQ_API_KEY з .env

MODEL = "openai/gpt-oss-120b"
SYSTEM_PROMPT = (
    "Ти NUYRA — помічник. Відповідай тією мовою, якою пише користувач: "
    "українською або англійською. Для дати й часу, обчислень і погоди "
    "завжди користуйся інструментами, а не вгадуй."
)
MAX_TOOL_STEPS = 5  # скільки разів поспіль модель може викликати інструменти
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


def run_agent(history):
    """Цикл агента: модель або відповідає, або просить викликати інструмент.
    Ми викликаємо його, додаємо результат в історію і питаємо модель знову."""
    for _ in range(MAX_TOOL_STEPS):
        message = client.chat.completions.create(
            model=MODEL, messages=history, tools=TOOLS
        ).choices[0].message
        if not message.tool_calls:
            return message.content  # інструменти не потрібні — це фінальна відповідь

        # запам'ятовуємо, які інструменти модель попросила…
        history.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [call.model_dump() for call in message.tool_calls],
        })
        # …і додаємо результат кожного з них
        for call in message.tool_calls:
            history.append({
                "role": "tool",
                "tool_call_id": call.id,  # щоб модель знала, на який виклик це відповідь
                "content": run_tool(call.function.name, call.function.arguments),
            })

    return "Вибач, я заплуталась в інструментах. Спробуй перефразувати питання."


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
        answer = run_agent(history)
    except APIError:
        raise HTTPException(status_code=502, detail="Groq не відповів, спробуй ще раз")

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
