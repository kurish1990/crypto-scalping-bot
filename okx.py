import ccxt
import websocket
import json
import time
from datetime import datetime, timezone

# Ваши API ключи для OKX
api_key = "api_key"
api_secret = "api_secret"
api_passphrase = "api_passphrase"

# Конфигурация
symbol = "AEVO/USDT"
min_trade_amount = 3  # Минимальное количество для торговли BTC
analyze_interval = 5  # Интервал анализа стакана в секундах

# Инициализация ccxt для OKX
exchange = ccxt.okx({
    'apiKey': api_key,
    'secret': api_secret,
    'password': api_passphrase,
    'enableRateLimit': True
})

# Проверка подключения
try:
    balance = exchange.fetch_balance()
    print("API подключение успешно.")
except Exception as e:
    print("Ошибка подключения к API:", e)
    exit()

# Глобальные переменные для позиции
active_position = None
entry_price = None
profit_price = None
terminate_after_trade = False

# Функция поиска крупных стенок в стакане
def find_walls(order_book):
    bids = order_book['bids']  # Покупки
    asks = order_book['asks']  # Продажи

    # Поиск стенок в покупках и продажах
    max_bid = max(bids, key=lambda x: float(x[1]), default=None)
    max_ask = max(asks, key=lambda x: float(x[1]), default=None)

    return max_bid, max_ask

# Функция проверки исполнения ордера
def check_order_filled(order_id):
    try:
        order = exchange.fetch_order(order_id, symbol)
        return order['status'] == 'closed'
    except Exception as e:
        print("Ошибка при проверке статуса ордера:", e)
        return False

# Функция обработки новых данных стакана
def on_message(ws, message):
    global active_position, entry_price, profit_price, terminate_after_trade

    try:
        data = json.loads(message)

        if "data" in data:
            if "asks" in data["data"][0] and "bids" in data["data"][0]:
                order_book = {
                    "bids": data["data"][0]["bids"],
                    "asks": data["data"][0]["asks"]
                }

                # Анализ стакана
                max_bid, max_ask = find_walls(order_book)

                if max_bid and max_ask and not active_position:
                    bid_price, bid_volume = float(max_bid[0]), float(max_bid[1])
                    ask_price, ask_volume = float(max_ask[0]), float(max_ask[1])

                    # Проверяем условия для открытия позиции
                    if bid_volume > 10 * min_trade_amount:
                        try:
                            buy_order = exchange.create_limit_buy_order(symbol, min_trade_amount, bid_price)
                            print(f"Ордер на покупку выставлен по цене: {bid_price:.2f}, ожидание исполнения...")
                            while not check_order_filled(buy_order['id']):
                                time.sleep(1)

                            entry_price = bid_price
                            profit_price = ask_price  # Продать перед стеной продаж
                            active_position = {
                                "amount": min_trade_amount,
                                "entry_price": entry_price
                            }
                            print(f"Ордер на покупку исполнен по цене: {entry_price:.2f}")
                        except Exception as e:
                            print("Ошибка при выставлении ордера на покупку:", e)

                # Если позиция открыта, проверяем условия выхода
                elif active_position:
                    try:
                        sell_order = exchange.create_limit_sell_order(symbol, active_position["amount"], profit_price)
                        print(f"Ордер на продажу выставлен по цене: {profit_price:.2f}, ожидание исполнения...")
                        while not check_order_filled(sell_order['id']):
                            time.sleep(1)

                        print(f"Продано по цене: {profit_price:.2f}, прибыль: {profit_price - entry_price:.2f}")
                        active_position = None
                        terminate_after_trade = True
                    except Exception as e:
                        print("Ошибка при продаже:", e)

            # Завершение работы после сделки
            if terminate_after_trade:
                print("Скрипт завершает работу после выполнения сделки.")
                ws.close()

    except Exception as e:
        print("Ошибка обработки сообщения WebSocket:", e)

# Функция обработки ошибок WebSocket
def on_error(ws, error):
    print("WebSocket ошибка:", error)

# Функция при закрытии WebSocket
def on_close(ws, close_status_code, close_msg):
    print("WebSocket закрыт")

# Функция при подключении WebSocket
def on_open(ws):
    print("WebSocket подключен")
    # Подписываемся на данные стакана
    subscribe_message = {
        "op": "subscribe",
        "args": [
            {
                "channel": "books5",
                "instId": symbol.replace("/", "-")
            }
        ]
    }
    ws.send(json.dumps(subscribe_message))

# Инициализация WebSocket
socket = "wss://ws.okx.com:8443/ws/v5/public"
ws = websocket.WebSocketApp(
    socket,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)
ws.on_open = on_open

# Запуск WebSocket
while True:
    try:
        ws.run_forever()
    except Exception as e:
        print("Ошибка WebSocket, переподключение:", e)
        time.sleep(5)
