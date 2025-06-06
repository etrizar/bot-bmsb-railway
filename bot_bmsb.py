import ccxt
import pandas as pd
import time
import datetime
import csv
import os
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode
import asyncio

# Cargar variables desde .env
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
CAPITAL_TOTAL = float(os.getenv("CAPITAL", 100))
RIESGO_POR_OPERACION = float(os.getenv("RIESGO", 0.02))
TAKE_PROFIT_PORCENTAJE = float(os.getenv("TAKE_PROFIT", 0.02))
STOP_LOSS_PORCENTAJE = float(os.getenv("STOP_LOSS", 0.01))
MARGEN_COMPRA = CAPITAL_TOTAL * RIESGO_POR_OPERACION

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot_telegram = Bot(token=TELEGRAM_TOKEN)

# 🔵 Mostrar configuración inicial
print(f"🔹 Capital total: ${CAPITAL_TOTAL:.2f}")
print(f"🔹 Monto a operar por operación: ${MARGEN_COMPRA:.2f}")
print(f"🔹 Riesgo por operación: {RIESGO_POR_OPERACION * 100:.2f}%")
print(f"🎯 Take Profit configurado: {TAKE_PROFIT_PORCENTAJE * 100:.2f}%")
print(f"🛡️ Stop Loss configurado: {STOP_LOSS_PORCENTAJE * 100:.2f}%")

# 🔵 Enviar alerta inicial
async def alerta_inicio():
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                f"🚀 Bot iniciado correctamente\n"
                f"🔹 Capital total: ${CAPITAL_TOTAL:.2f}\n"
                f"🔹 Monto a operar: ${MARGEN_COMPRA:.2f}\n"
                f"🔹 Riesgo: {RIESGO_POR_OPERACION * 100:.2f}%\n"
                f"🎯 TP: {TAKE_PROFIT_PORCENTAJE * 100:.2f}% | 🛡️ SL: {STOP_LOSS_PORCENTAJE * 100:.2f}%"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"❌ Error al enviar alerta de inicio: {e}")

asyncio.run(alerta_inicio())

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

# Variables de operación
precio_compra = None
precio_tp = None
precio_sl = None
cantidad_operacion = None
operacion_abierta = False

# Función para enviar alertas
async def enviar_alerta(mensaje):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensaje, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"❌ Error al enviar alerta de Telegram: {e}")

# Función para registrar operación en CSV
def registrar_operacion(fecha_hora, tipo_cierre, precio_compra, precio_venta, variacion_pct, ganancia_perdida):
    archivo = 'registro_operaciones.csv'
    archivo_existe = os.path.isfile(archivo)

    with open(archivo, mode='a', newline='') as file:
        writer = csv.writer(file)
        
        if not archivo_existe:
            writer.writerow(['FechaHora', 'TipoCierre', 'PrecioCompra', 'PrecioVenta', 'Variacion(%)', 'GananciaPerdida(USD)'])
        
        writer.writerow([
            fecha_hora,
            tipo_cierre,
            f"{precio_compra:.2f}",
            f"{precio_venta:.2f}",
            f"{variacion_pct:.2f}",
            f"{ganancia_perdida:.2f}"
        ])

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
        asyncio.run(enviar_alerta(f"✅ ORDEN {tipo.upper()} ejecutada en {simbolo} por aproximadamente ${monto_usd:.2f}"))

        return precio_actual, cantidad

    except Exception as e:
        print(f"❌ Error al ejecutar orden: {e}")
        asyncio.run(enviar_alerta(f"❌ Error al ejecutar orden {tipo.upper()} en {simbolo}: {e}"))
        return None, None

def ejecutar_bot():
    global precio_compra, precio_tp, precio_sl, operacion_abierta, cantidad_operacion

    while True:
        try:
            df = obtener_datos(SIMBOLO)
            df = calcular_bms_band(df)
            df = generar_senales(df)
            ultima = df.iloc[-1]
            ticker = exchange.fetch_ticker(SIMBOLO)
            precio_actual = ticker['last']

            if operacion_abierta:
                if precio_actual >= precio_tp:
                    ganancia = (precio_actual - precio_compra) * cantidad_operacion
                    porcentaje = ((precio_actual / precio_compra) - 1) * 100
                    fecha_hora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    registrar_operacion(fecha_hora, 'Take Profit', precio_compra, precio_actual, porcentaje, ganancia)

                    print(f"🎯 Take Profit alcanzado. Ganancia: +${ganancia:.2f}")
                    asyncio.run(enviar_alerta(
                        f"🎯 <b>Take Profit alcanzado</b>\n"
                        f"Ganancia: +${ganancia:.2f} ({porcentaje:.2f}%)\n"
                        f"Precio de compra: {precio_compra:.2f}\n"
                        f"Precio de venta: {precio_actual:.2f}"
                    ))
                    ejecutar_orden('sell', SIMBOLO, cantidad_operacion * precio_actual)
                    operacion_abierta = False

                elif precio_actual <= precio_sl:
                    perdida = (precio_actual - precio_compra) * cantidad_operacion
                    porcentaje = ((precio_actual / precio_compra) - 1) * 100
                    fecha_hora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    registrar_operacion(fecha_hora, 'Stop Loss', precio_compra, precio_actual, porcentaje, perdida)

                    print(f"🛡️ Stop Loss alcanzado. Pérdida: {perdida:.2f}")
                    asyncio.run(enviar_alerta(
                        f"🛡️ <b>Stop Loss alcanzado</b>\n"
                        f"Pérdida: {perdida:.2f} ({porcentaje:.2f}%)\n"
                        f"Precio de compra: {precio_compra:.2f}\n"
                        f"Precio de venta: {precio_actual:.2f}"
                    ))
                    ejecutar_orden('sell', SIMBOLO, cantidad_operacion * precio_actual)
                    operacion_abierta = False

                else:
                    print(f"[{datetime.datetime.now()}] 📈 Operación abierta - Monitoreando precio...")

            else:
                if ultima['buy']:
                    print("📈 Señal de COMPRA detectada")
                    asyncio.run(enviar_alerta(f"📈 Señal de COMPRA detectada en {SIMBOLO}"))
                    precio_compra, cantidad_operacion = ejecutar_orden('buy', SIMBOLO, MARGEN_COMPRA)
                    if precio_compra:
                        precio_tp = precio_compra * (1 + TAKE_PROFIT_PORCENTAJE)
                        precio_sl = precio_compra * (1 - STOP_LOSS_PORCENTAJE)
                        operacion_abierta = True

                elif ultima['sell']:
                    print("📉 Señal de VENTA detectada (no se opera en venta si no hay posición)")

                else:
                    print(f"[{datetime.datetime.now()}] 🔄 Sin señales")

        except Exception as e:
            print(f"❌ Error general: {e}")
            asyncio.run(enviar_alerta(f"❌ Error general en bot: {e}"))

        time.sleep(300)  # Esperar 15 minutos antes de volver a analizar

if __name__ == '__main__':
    ejecutar_bot()
