import ccxt
import pandas as pd
import time
import datetime
from dotenv import load_dotenv
import os
from telegram import Bot
from telegram.constants import ParseMode
import asyncio

# Cargar variables desde .env
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
CAPITAL_TOTAL = float(os.getenv("CAPITAL", 100))
RIESGO_POR_OPERACION = float(os.getenv("RIESGO", 0.02))
MARGEN_COMPRA = CAPITAL_TOTAL * RIESGO_POR_OPERACION

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot_telegram = Bot(token=TELEGRAM_TOKEN)

# Configurar Binance real
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True
    }
})

SIMBOLO = 'BTC/USDT'

# Función para enviar alertas a Telegram
async def enviar_alerta(mensaje):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensaje, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"❌ Error al enviar alerta de Telegram: {e}")


def obtener_datos(simbolo, timeframe='15m', limite=100):
    velas = exchange.fetch_ohlcv(simbolo, timeframe=timeframe, limit=limite)
    df = pd.DataFrame(velas, columns=['timestamp', 'open', 'high', 'low', 'close', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calcular_bms_band(df):
    df['sma20'] = df['close'].rolling(window=20).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['bmsbmayor'] = df[['sma20', 'ema21']].max(axis=1)
    df['bmsbmenor'] = df[['sma20', 'ema21']].min(axis=1)
    return df

def generar_senales(df):
    df['buy'] = (df['close'].shift(1) < df['bmsbmayor'].shift(1)) & (df['close'] > df['bmsbmayor'])
    df['sell'] = (df['close'].shift(1) > df['bmsbmenor'].shift(1)) & (df['close'] < df['bmsbmenor'])
    return df

def ejecutar_orden(tipo, simbolo, monto_usd):
    ticker = exchange.fetch_ticker(simbolo)
    precio_actual = ticker['last']
    cantidad = round(monto_usd / precio_actual, 6)
    try:
        if tipo == 'buy':
            orden = exchange.create_market_buy_order(simbolo, cantidad)
        elif tipo == 'sell':
            orden = exchange.create_market_sell_order(simbolo, cantidad)

        print(f"[{datetime.datetime.now()}] ✅ Orden {tipo.upper()} ejecutada: {orden}")
        asyncio.run(enviar_alerta(f"✅ ORDEN {tipo.upper()} ejecutada en {simbolo} por aproximadamente ${monto_usd:.2f}"))

    except Exception as e:
        print(f"❌ Error al ejecutar orden: {e}")
        asyncio.run(enviar_alerta(f"❌ Error al ejecutar orden {tipo.upper()} en {simbolo}: {e}"))

def ejecutar_bot():
    while True:
        try:
            df = obtener_datos(SIMBOLO)
            df = calcular_bms_band(df)
            df = generar_senales(df)
            ultima = df.iloc[-1]

            if ultima['buy']:
                print("📈 Señal de COMPRA detectada")
                enviar_alerta(f"📈 Señal de COMPRA detectada en {SIMBOLO}")
                ejecutar_orden('buy', SIMBOLO, MARGEN_COMPRA)

            elif ultima['sell']:
                print("📉 Señal de VENTA detectada")
                enviar_alerta(f"📉 Señal de VENTA detectada en {SIMBOLO}")
                ejecutar_orden('sell', SIMBOLO, MARGEN_COMPRA)

            else:
                print(f"[{datetime.datetime.now()}] 🔄 Sin señales")

        except Exception as e:
            print(f"❌ Error general: {e}")
            enviar_alerta(f"❌ Error general en bot: {e}")

        time.sleep(900)  # Esperar 15 minutos antes de volver a analizar

if __name__ == '__main__':
    ejecutar_bot()

