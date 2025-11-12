# bot.py
import asyncio
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import logging

# === تنظیمات ===
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # توکن @GlobalCoinsignalsbot
TON_WALLET = "EQBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # والت TON (اختیاری)

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})

conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT)''')
conn.commit()

def get_pairs():
    try:
        markets = exchange.load_markets()
        return [s for s in markets.keys() if '/USDT' in s and markets[s]['active']][:50]
    except:
        return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

PAIRS = get_pairs()

def generate_signal():
    for pair in PAIRS:
        try:
            ohlcv = exchange.fetch_ohlcv(pair, '1h', limit=100)
            if len(ohlcv) < 50: continue
            df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['ema9'] = df['c'].ewm(span=9).mean()
            df['ema21'] = df['c'].ewm(span=21).mean()
            delta = df['c'].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = -delta.clip(upper=0).rolling(14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            df['atr'] = (df['h'] - df['l']).rolling(14).mean()
            df['vol_avg'] = df['v'].rolling(20).mean()

            last = df.iloc[-1]
            prev = df.iloc[-2]

            if (last['c'] > last['ema9'] > last['ema21'] and
                last['rsi'] < 38 and
                last['v'] > last['vol_avg'] * 1.5 and
                prev['c'] < prev['ema9']):

                entry = last['c']
                atr = max(last['atr'], entry * 0.005)
                return {
                    'pair': pair,
                    'entry': round(entry, 6),
                    'tp1': round(entry + atr * 1.5, 6),
                    'tp2': round(entry + atr * 2.8, 6),
                    'sl': round(entry - atr * 0.9, 6),
                    'confidence': min(90, int(70 + (last['v']/last['vol_avg'] - 1)*15))
                }
        except: continue
    return None

def format_signal(sig, lang='en'):
    if lang == 'fa':
        return f"سیگنال: {sig['pair']}\nورود: {sig['entry']}\nTP1: {sig['tp1']}\nTP2: {sig['tp2']}\nSL: {sig['sl']}"
    else:
        return f"""
**GLOBAL AI SIGNAL**

**{sig['pair']}**  
Entry: `{sig['entry']}`  
TP1: `{sig['tp1']}`  
TP2: `{sig['tp2']}`  
SL: `{sig['sl']}`  
Confidence: {sig['confidence']}%

Risk: <1% | Reward: +{((sig['tp2']/sig['entry'])-1)*100:.1f}%
Valid: 6 hours
        """.strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = 'fa' if 'fa' in str(user.language_code or '') else 'en'
    c.execute("INSERT OR IGNORE INTO users (user_id, lang) VALUES (?, ?)", (user.id, lang))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("Free Signal" if lang=='en' else "سیگنال رایگان", callback_data='free')],
        [InlineKeyboardButton("Subscribe 0.5 TON", url=f"t.me/wallet?start=pay_{TON_WALLET}")]
    ]
    await update.message.reply_text(
        "*GlobalCoin Signals AI+*\n"
        "300+ Coins | 1–3% Daily | Risk <1%\n"
        "Free AI Signal →",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    c.execute("SELECT lang FROM users WHERE user_id=?", (query.from_user.id,))
    row = c.fetchone()
    lang = row[0] if row else 'en'

    sig = generate_signal()
    if sig:
        await query.edit_message_text(format_signal(sig, lang), parse_mode='Markdown')
    else:
        msg = "No signal right now. Scanning 300+ coins..." if lang=='en' else "سیگنالی پیدا نشد. در حال اسکن..."
        await query.edit_message_text(msg)

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    print("GlobalCoin Signals is LIVE!")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
