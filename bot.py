
import os
import time
import requests
import pandas as pd
import numpy as np

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

PAIRS = {
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
    "AUD/USD": "AUD/USD",
}

CHECK_EVERY = 60
MIN_SCORE = 75
last_signal = {}


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": message},
            timeout=15
        )
    except Exception as e:
        print("Telegram error:", e)


def get_candles(symbol):
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "5min",
        "outputsize": 150,
        "apikey": TWELVE_API_KEY,
        "format": "JSON"
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        data = response.json()

        if "values" not in data:
            print("API error:", data)
            return None

        df = pd.DataFrame(data["values"])

        for column in ["open", "high", "low", "close"]:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df = df.sort_values("datetime")
        df = df.reset_index(drop=True)

        return df

    except Exception as e:
        print("Market data error:", e)
        return None


def calculate_ema(series, period):
    return series.ewm(
        span=period,
        adjust=False
    ).mean()


def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    average_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    average_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = average_gain / average_loss.replace(
        0,
        np.nan
    )

    return 100 - (100 / (1 + rs))


def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]

    high_close = abs(
        df["high"] - df["close"].shift()
    )

    low_close = abs(
        df["low"] - df["close"].shift()
    )

    true_range = pd.concat(
        [high_low, high_close, low_close],
        axis=1
    ).max(axis=1)

    return true_range.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


def analyze_market(df):

    if df is None or len(df) < 100:
        return None

    df = df.copy()

    df["EMA20"] = calculate_ema(
        df["close"],
        20
    )

    df["EMA50"] = calculate_ema(
        df["close"],
        50
    )

    df["RSI"] = calculate_rsi(
        df["close"]
    )

    df["ATR"] = calculate_atr(df)

    current = df.iloc[-1]
    previous = df.iloc[-2]

    buy_score = 0
    sell_score = 0

    # الاتجاه العام
    if current["EMA20"] > current["EMA50"]:
        buy_score += 20

    elif current["EMA20"] < current["EMA50"]:
        sell_score += 20

    # RSI
    if 50 < current["RSI"] < 70:
        buy_score += 15

    elif 30 < current["RSI"] < 50:
        sell_score += 15

    # حركة السعر
    if current["close"] > previous["close"]:
        buy_score += 15

    elif current["close"] < previous["close"]:
        sell_score += 15

    # أعلى وأدنى مستوى قريب
    recent_high = df["high"].iloc[-11:-1].max()
    recent_low = df["low"].iloc[-11:-1].min()

    # اختراق صاعد
    if current["close"] > recent_high:
        buy_score += 30

    # كسر هابط
    if current["close"] < recent_low:
        sell_score += 30

    # قوة الشمعة
    candle_range = (
        current["high"] -
        current["low"]
    )

    if candle_range > 0:

        body = abs(
            current["close"] -
            current["open"]
        )

        body_ratio = body / candle_range

        if body_ratio >= 0.60:

            if current["close"] > current["open"]:
                buy_score += 20

            elif current["close"] < current["open"]:
                sell_score += 20

    if buy_score >= MIN_SCORE and buy_score > sell_score:
        return "BUY", buy_score, current

    if sell_score >= MIN_SCORE and sell_score > buy_score:
        return "SELL", sell_score, current

    return None


def send_signal(pair, signal, score, candle):

    if signal == "BUY":
        direction = "🟢 شراء / CALL"
    else:
        direction = "🔴 بيع / PUT"

    message = f"""
🚨 Eyad Trader Bot

💱 السوق: {pair}
⏱ الفريم: M5

📌 الإشارة:
{direction}

🎯 قوة الإشارة:
{score}/100

🕐 الدخول:
الآن عند ظهور الإشارة

⌛ مدة الصفقة:
5–10 دقائق

💰 السعر:
{candle["close"]}

📊 التحليل:
• EMA20 / EMA50
• RSI
• حركة السعر
• كسر مستوى
• قوة الشمعة

⚠️ إشارة تحليلية وليست ضمانًا للربح.
"""

    send_telegram(message)


def main():

    send_telegram(
        "🤖 Eyad Trader Bot\n\n"
        "✅ بدأ المراقبة تلقائيًا\n"
        "⏱ M5\n"
        "📊 EUR/USD\n"
        "📊 GBP/USD\n"
        "📊 USD/JPY\n"
        "📊 AUD/USD"
    )

    while True:

        for pair, symbol in PAIRS.items():

            try:

                candles = get_candles(symbol)

                result = analyze_market(candles)

                if result:

                    signal, score, candle = result

                    signal_id = (
                        f"{pair}_"
                        f"{signal}_"
                        f"{candle['datetime']}"
                    )

                    if last_signal.get(pair) != signal_id:

                        send_signal(
                            pair,
                            signal,
                            score,
                            candle
                        )

                        last_signal[pair] = signal_id

            except Exception as error:

                print(
                    f"{pair} error:",
                    error
                )

        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
