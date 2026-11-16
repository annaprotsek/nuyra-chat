import ast
import json
import operator
from datetime import datetime

import httpx


# ---------- 🕐 дата й час ----------

def get_current_datetime():
    """Поточні дата й час на комп'ютері, де працює сервер."""
    now = datetime.now().astimezone()  # astimezone() — щоб знати свій часовий пояс
    return now.strftime("%Y-%m-%d %H:%M, %A, UTC%z")


# ---------- 🧮 калькулятор ----------

# які знаки дозволені і яка Python-функція їх рахує
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,  # мінус перед числом: -5
    ast.UAdd: operator.pos,  # плюс перед числом: +5
}


def calculate(expression):
    """Рахує вираз на кшталт "(17.5 * 3) ** 2" без eval():
    розбираємо вираз на дерево і дозволяємо лише числа та знаки з OPERATORS."""
    tree = ast.parse(expression, mode="eval")
    return evaluate(tree.body)


def evaluate(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        left, right = evaluate(node.left), evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Занадто великий степінь")  # 9 ** 9 ** 9 повісив би сервер
        return OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
        return OPERATORS[type(node.op)](evaluate(node.operand))
    raise ValueError("Дозволені лише числа та + - * / ** % ()")


# ---------- 🌤 погода (Open-Meteo, ключ не потрібен) ----------

# Open-Meteo повертає погоду числовим кодом — перекладаємо в слова
WEATHER_CODES = {
    0: "ясно", 1: "переважно ясно", 2: "мінлива хмарність", 3: "хмарно",
    45: "туман", 48: "туман з інеєм",
    51: "легка мряка", 53: "мряка", 55: "сильна мряка",
    61: "невеликий дощ", 63: "дощ", 65: "сильний дощ",
    71: "невеликий сніг", 73: "сніг", 75: "сильний сніг", 77: "снігова крупа",
    80: "короткочасний дощ", 81: "злива", 82: "сильна злива",
    85: "снігопад", 86: "сильний снігопад",
    95: "гроза", 96: "гроза з градом", 99: "сильна гроза з градом",
}


def get_weather(city):
    """Погода зараз: спершу знаходимо координати міста, потім погоду за ними."""
    places = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "uk"},
        timeout=10,
    ).json().get("results")
    if not places:
        return f"Місто «{city}» не знайдено"
    place = places[0]

    current = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        },
        timeout=10,
    ).json()["current"]

    return {
        "місто": f"{place['name']}, {place.get('country', '')}",
        "температура_C": current["temperature_2m"],
        "відчувається_як_C": current["apparent_temperature"],
        "опис": WEATHER_CODES.get(current["weather_code"], "невідомо"),
        "вітер_км_год": current["wind_speed_10m"],
    }


# ---------- опис інструментів для моделі ----------

# з цього опису модель дізнається, які інструменти є і коли їх викликати
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Поточні дата, час і день тижня. Викликай, коли питають про сьогодні, зараз, дату чи час.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Точно рахує арифметичний вираз. Викликай для будь-яких обчислень.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Вираз з чисел і + - * / ** % (), напр. (17.5 * 3) ** 2",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Погода зараз у місті: температура, опис, вітер.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Назва міста, напр. Київ або London"},
                },
                "required": ["city"],
            },
        },
    },
]

FUNCTIONS = {
    "get_current_datetime": get_current_datetime,
    "calculate": calculate,
    "get_weather": get_weather,
}


def run_tool(name, arguments_json):
    """Викликає інструмент за назвою, яку обрала модель.
    Помилку повертаємо моделі текстом — вона сама пояснить її користувачу."""
    try:
        arguments = json.loads(arguments_json or "{}")
        result = FUNCTIONS[name](**arguments)
    except Exception as error:
        result = f"Помилка: {error}"
    return json.dumps(result, ensure_ascii=False)
