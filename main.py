import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from collections import defaultdict
from openai import OpenAI
import logging
import db

# logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# consts
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_TOKEN = os.getenv("OPENAI_API_KEY")

# gpt
client = OpenAI(
    api_key=OPENAI_TOKEN,
    base_url="https://api.chatanywhere.org/v1" 
)

def gpt_35_api_stream(messages: list) -> str:
    try:
        stream = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=messages,
            stream=True,
        )
        full_response = ""
        print("\n[GPT-Ответ]: ", end="")
        
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                # log response
                print(content, end="", flush=True) 
                # response response
                full_response += content 
        
        print() 
        return full_response
    except Exception as e:
        logger.error(f"Ошибка при обращении к OpenAI API: {e}")
        return f"GPT_ERROR: Произошла ошибка при получении ответа: {e}"

# tg 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Чтобы очистить историю, используй команду /reset."
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await db.delete_history(chat_id)
    await update.message.reply_text("🗑️ История чата очищена. Можешь начать новую тему.")

# message handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_message = update.message.text
    logger.info(f"Получено сообщение от чата {chat_id}: {user_message}")

    chat_history = await db.get_history(chat_id) 

    chat_history.append({"role": "user", "content": user_message})
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    bot_reply = await asyncio.to_thread(gpt_35_api_stream, chat_history)

    if bot_reply.startswith("GPT_ERROR:"):
        await update.message.reply_text(f"❌ {bot_reply}")
        chat_history.pop() 
        logger.warning(f"Ошибка GPT в чате {chat_id}. Сообщение пользователя удалено из истории.")
    else:
        chat_history.append({"role": "assistant", "content": bot_reply})
        
        await db.save_history(chat_id, chat_history)
        
        await update.message.reply_text(bot_reply)
        logger.info(f"Ответ GPT отправлен в чат {chat_id}.")

async def post_init(application):
    await db.init_db_pool()
    logger.info("база данных инициализирована.")
    
async def post_shutdown(application):
    await db.close_db_pool()
    logger.info("пул подключений PostgreSQL корректно закрыт.")

if __name__ == "__main__":
    if not TG_TOKEN or not OPENAI_TOKEN:
        print("tokens error")
        exit(1)
    
    app = (
            ApplicationBuilder()
            .token(TG_TOKEN)
            .post_init(post_init) 
            .post_shutdown(post_shutdown)
            .build()
        )

    # sync handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен и готов принимать сообщения...")
    logger.info("Бот запущен.")
    app.run_polling()
