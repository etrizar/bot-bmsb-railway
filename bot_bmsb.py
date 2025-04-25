import ccxt
import pandas as pd
import time
import datetime
from dotenv import load_dotenv
import os

# Cargar variables desde .env
load_dotenv()  # ← Esto es obligatorio

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
CAPITAL_TOTAL = float(os.getenv("CAPITAL", 100))
RIESGO_POR_OPERACION = float(os.getenv("RIESGO", 0.02))
MARGEN_COMPRA = CAPITAL_TOTAL * RIESGO_POR_OPERACION

# Configurar Binance Testnet
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
exchange.set_sandbox_mode(True)

SIMBOLO = 'BTC/USDT'

def obtener_datos(simbolo, timeframe='15m', limite=100):
    velas = exchange.fetch_ohlcv(simbolo, timeframe=timeframe, limit=limite)
    df = pd.DataFrame(velas, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
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
    except Exception as e:
        print(f"❌ Error al ejecutar orden: {e}")

def ejecutar_bot():
    while True:
        try:
            df = obtener_datos(SIMBOLO)
            df = calcular_bms_band(df)
            df = generar_senales(df)
            ultima = df.iloc[-1]

            if ultima['buy']:
                print("📈 Señal de COMPRA detectada")
                ejecutar_orden('buy', SIMBOLO, MARGEN_COMPRA)
            elif ultima['sell']:
                print("📉 Señal de VENTA detectada")
                ejecutar_orden('sell', SIMBOLO, MARGEN_COMPRA)
            else:
                print(f"[{datetime.datetime.now()}] 🔄 Sin señales")

        except Exception as e:
            print(f"❌ Error: {e}")

        time.sleep(900)  # Espera 15 minutos

if __name__ == '__main__':
    ejecutar_bot()
