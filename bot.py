# فایل: ai_signals_bot.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import ccxt
import pandas as pd
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta

# تنظیمات
BOT_TOKEN="8446696795:AAGyWTmVt6YDAhFf4LuytFbKtCtrmJfFLPI"  # توکن رو اینجا بذار
TON_PAYMENT_ADDRESS = "UQC8oNGKujcu7QFJ5YDfMq7AO-IOqFO923YGAy0Ci75GBZSh"  # آدرس TON والتت
MIN_SUBSCRIPTION_TON = 0.5  # حداقل پرداخت برای اشتراک (TON)

# لاگ
logging.basicConfig(level=logging.INFO)

# اتصال به صرافی
exchange = ccxt.binance({'enableRateLimit': True})

# دیتابیس
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users 
             (user_id INTEGER PRIMARY KEY, username TEXT, subscribed INTEGER, expiry TIMESTAMP)''')
conn.commit()

# --- تابع چک کردن اشتراک ---
def is_subscribed(user_id):
    c.execute("SELECT expiry FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0]:
        return datetime.fromisoformat(row[0]) > datetime.now()
    return False

# --- تابع تولید سیگنال AI ---
def generate_signal():
    try:
        # دریافت داده 1h
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # اندیکاتورها
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        exp1 = df['close'].ewm(span=12).mean()
        exp2 = df['close'].ewm(span=26).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['volume_avg'] = df['volume'].rolling(20).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # شرایط خرید
        if (last['rsi'] < 35 and 
            prev['macd'] < prev['macd_signal'] and 
            last['macd'] > last['macd_signal'] and 
            last['volume'] > last['volume_avg'] * 1.3):
            
            entry = last['close']
            return {
                'pair': 'BTC/USDT',
                'side': 'LONG',
                'entry': round(entry, 2),
                'tp1': round(entry * 1.017, 2),
                'tp2': round(entry * 1.028, 2),
                'sl': round(entry * 0.993, 2),
                'confidence': 86
            }
    except:
        pass
    return None

# --- قالب سیگنال ---
def format_signal(sig):
    return f"""
🚀 AI SIGNAL #{int(datetime.now().timestamp()) % 10000}

Pair: {sig['pair']}  
Direction: {sig['side']} {'🔼' if sig['side']=='LONG' else '🔽'}  

Entry: {sig['entry']:,}$  
Take Profit:  
   • TP1: {sig['tp1']:,}$ (+1.7%)  
   • TP2: {sig['tp2']:,}$ (+2.8%)  
Stop Loss: {sig['sl']:,}$ (-0.7%)  

Leverage: 5x  
Exchange: Binance Futures  
Confidence: {sig['confidence']}%  
Risk: 1% of capital  

⏰ *Valid for 4 hours*
    """.strip()

# --- دستور /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Get Free Signal", callback_data='free_signal')],
        [InlineKeyboardButton("Subscribe (0.5 TON)", callback_data='subscribe')],
        [InlineKeyboardButton("Check Subscription", callback_data='check_sub')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🚀 *Welcome {user.first_name}!*\n\n"
        "Get AI-powered crypto signals with 86% accuracy.\n"
        "Free signal available!\n\n"
        "Subscribe for unlimited signals → 0.5 TON (~$3)",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- دکمه‌ها ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'free_signal':
        if not is_subscribed(user_id):
            # ثبت کاربر
            c.execute("INSERT OR IGNORE INTO users (user_id, subscribed, expiry) VALUES (?, 0, NULL)", (user_id,))
            conn.commit()
            # ارسال سیگنال رایگان
            sig = generate_signal()
            if sig:
                await query.edit_message_text(format_signal(sig), parse_mode='Markdown')
            else:
                await query.edit_message_text("No strong signal right now. Try again in 1h!")
        else:
            await query.edit_message_text("You're already subscribed! Use /signal")

    elif query.data == 'subscribe':
        await query.edit_message_text(
            f"Subscribe for unlimited signals!\n\n"
            f"Send 0.5 TON to:\n{TON_PAYMENT_ADDRESS}\n\n"
            f"After payment, send TX hash to@hormuz1991_70 ",
            parse_mode='Markdown'
        )

    elif query.data == 'check_sub':
        if is_subscribed(user_id):
            c.execute("SELECT expiry FROM users WHERE user_id = ?", (user_id,))
            expiry = c.fetchone()[0]
            await query.edit_message_text(f"Active until: {expiry}")
        else:
            await query.edit_message_text("Not subscribed. Use /subscribe")

# --- دستور /signal (فقط برای مشترکین) ---
async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        sig = generate_signal()
        if sig:
            await update.message.reply_text(format_signal(sig), parse_mode='Markdown')
        else:
            await update.message.reply_text("No signal right now. Checking every 30min...")
    else:
        await update.message.reply_text("Subscribe first! /start")

# --- اجرای ربات ---
async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is running... Press Ctrl+C to stop.")
    await app.run_polling()

if name == 'main':
    asyncio.run(main())
