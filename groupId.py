from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

BOT_TOKEN = '7381440694:AAGZp0Xwurd-ErSOXLsQRWW1Nu0a3N8I3to'

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Chat ID:", update.effective_chat.id)
    print("Chat Title:", update.effective_chat.title)
    print("User:", update.effective_user.full_name)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, get_chat_id))

    print("Bot is running... Send a message in the group.")
    app.run_polling()
