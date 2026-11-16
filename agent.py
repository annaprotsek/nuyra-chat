from dotenv import load_dotenv
from groq import Groq

load_dotenv()  # читаємо змінні з .env (там GROQ_API_KEY)

client = Groq()  # підключаємось до Groq (ключ береться з GROQ_API_KEY)

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "system", "content": "Ти помічник. Відповідай коротко українською."},
        {"role": "user", "content": "Напиши закон збереження енергіїІ"},
    ],
)
print(response.choices[0].message.content)  # показати відповідь