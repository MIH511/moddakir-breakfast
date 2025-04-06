import datetime
import json
import os
import re
from collections import Counter, defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from pytz import timezone
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot credentials
BOT_TOKEN = '7381440694:AAGZp0Xwurd-ErSOXLsQRWW1Nu0a3N8I3to'
GROUP_CHAT_ID = -1002642403478

# Constants
ORDER_STATE_FILE = "order_state.json"
COLLECTION_TIME_MINUTES = 30  # How long to collect orders after reminder
ADMIN_USER_IDS = []  # Add admin user IDs here if needed

# Order state management
order_state = {
    "is_collecting": False,
    "orders": {},  # {user_id: {"name": name, "order": order}}
    "collection_end_time": None
}


# Save and load state functions
def save_state():
    with open(ORDER_STATE_FILE, 'w') as f:
        # Convert datetime to string for JSON serialization
        state_copy = order_state.copy()
        if state_copy["collection_end_time"]:
            state_copy["collection_end_time"] = state_copy["collection_end_time"].isoformat()
        json.dump(state_copy, f)


def load_state():
    global order_state
    if os.path.exists(ORDER_STATE_FILE):
        with open(ORDER_STATE_FILE, 'r') as f:
            state = json.load(f)
            # Convert string back to datetime if needed
            if state["collection_end_time"]:
                state["collection_end_time"] = datetime.datetime.fromisoformat(state["collection_end_time"])
            order_state = state


# Parse order text to extract quantities and items
def parse_order(order_text):
    # Updated parser that handles non-Latin characters including Arabic
    items = []

    # Look for patterns like "2x burger", "2 burger", etc.
    # Modified regex to include non-Latin characters
    quantity_matches = re.finditer(r'(\d+)\s*(?:x\s*)?([^\d\n]+)', order_text)
    for match in quantity_matches:
        quantity = int(match.group(1))
        item = match.group(2).strip().lower()
        items.extend([item] * quantity)

    # If no quantity patterns found, treat it as a single item
    if not items:
        items = [order_text.strip().lower()]

    return items


# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm a food order bot. I'll send reminders for food orders and collect responses."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Food Order Bot Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/order [your order] - Place your food order (e.g., '2x burger and fries')\n"
        "/cancel - Cancel your order\n"
        "/summary - Show all current orders\n"
        "/collect - Manually start collecting orders (admin only)\n"
        "/close - Manually stop collecting orders (admin only)\n"
        "/recite - Generate a consolidated receipt (admin only)"
    )
    await update.message.reply_text(help_text)


async def place_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not order_state["is_collecting"]:
        await update.message.reply_text("Sorry, we're not collecting orders right now!")
        return

    user = update.effective_user
    order_text = " ".join(context.args) if context.args else "No details provided"

    order_state["orders"][str(user.id)] = {
        "name": user.first_name,
        "order": order_text
    }
    save_state()

    await update.message.reply_text(f"Your order has been placed: {order_text}")


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if user_id in order_state["orders"]:
        del order_state["orders"][user_id]
        save_state()
        await update.message.reply_text("Your order has been canceled.")
    else:
        await update.message.reply_text("You don't have an active order.")


async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not order_state["orders"]:
        await update.message.reply_text("No orders have been placed yet.")
        return

    summary = "📋 Current Orders:\n\n"
    for user_id, details in order_state["orders"].items():
        summary += f"• {details['name']}: {details['order']}\n"

    if order_state["is_collecting"] and order_state["collection_end_time"]:
        end_time = order_state["collection_end_time"]
        remaining = end_time - datetime.datetime.now(end_time.tzinfo)
        minutes_remaining = int(remaining.total_seconds() / 60)
        summary += f"\nOrder collection ends in {minutes_remaining} minutes."

    await update.message.reply_text(summary)


async def generate_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is admin (optional)
    # user_id = str(update.effective_user.id)
    # if ADMIN_USER_IDS and user_id not in ADMIN_USER_IDS:
    #     await update.message.reply_text("Only admins can generate receipts.")
    #     return

    if not order_state["orders"]:
        await update.message.reply_text("No orders have been placed yet.")
        return

    # Track items and who ordered them
    all_items = []
    item_customers = defaultdict(list)

    # Collect and parse all orders
    for user_id, details in order_state["orders"].items():
        user_name = details['name']
        order_items = parse_order(details['order'])

        for item in order_items:
            all_items.append(item)
            item_customers[item].append(user_name)

    # Count items
    item_counts = Counter(all_items)

    # Generate receipt
    receipt = "🧾 **ORDER RECEIPT**\n\n"

    # Total items section
    receipt += "📋 **TOTAL ITEMS:**\n"
    for item, count in sorted(item_counts.items(), key=lambda x: x[1], reverse=True):
        receipt += f"• {count}x {item}\n"

    receipt += "\n📝 **WHO ORDERED WHAT:**\n"
    for item, customers in sorted(item_customers.items()):
        customer_counts = Counter(customers)
        customer_text = ", ".join([f"{name} ({count}x)" if count > 1 else name
                                   for name, count in customer_counts.items()])
        receipt += f"• {item}: {customer_text}\n"

    await update.message.reply_text(receipt)


async def start_collection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Could add admin check here
    order_state["is_collecting"] = True
    order_state["orders"] = {}
    cairo_tz = timezone("Africa/Cairo")
    order_state["collection_end_time"] = datetime.datetime.now(cairo_tz) + datetime.timedelta(
        minutes=COLLECTION_TIME_MINUTES)
    save_state()

    # Create inline keyboard for quick ordering
    keyboard = [
        [InlineKeyboardButton("Place Order", callback_data="place_order")],
        [InlineKeyboardButton("See Current Orders", callback_data="view_orders")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🍔 Food order collection started! Please place your orders within {COLLECTION_TIME_MINUTES} minutes.\n"
        f"Use /order [your food request] to place an order.",
        reply_markup=reply_markup
    )


async def close_collection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Could add admin check here
    if not order_state["is_collecting"]:
        await update.message.reply_text("No active order collection to close.")
        return

    await end_collection(context)
    await update.message.reply_text("Order collection has been closed.")


async def end_collection(context: ContextTypes.DEFAULT_TYPE):
    order_state["is_collecting"] = False

    # Generate final order summary
    if order_state["orders"]:
        summary = "📋 Final Order Summary:\n\n"
        for user_id, details in order_state["orders"].items():
            summary += f"• {details['name']}: {details['order']}\n"

        # Add instructions for generating receipt
        summary += "\nAdmin can type /recite to generate a consolidated receipt."

        # Send the summary to the group
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=summary)
    else:
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="No orders were placed.")

    save_state()


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "place_order":
        await query.message.reply_text("Please reply with /order followed by your food request.")
    elif query.data == "view_orders":
        # Create a temporary Update object to reuse show_summary
        temp_update = Update(update_id=0, callback_query=query)
        await show_summary(temp_update, context)


async def check_collection_timeout(context: ContextTypes.DEFAULT_TYPE):
    if (order_state["is_collecting"] and order_state["collection_end_time"] and
            datetime.datetime.now(order_state["collection_end_time"].tzinfo) >= order_state["collection_end_time"]):
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text="⏰ Time's up! Order collection is now closed."
        )
        await end_collection(context)


async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    # Get current day in Cairo timezone
    cairo_tz = timezone("Africa/Cairo")
    now = datetime.datetime.now(cairo_tz)
    day_of_week = now.weekday()  # 0 is Monday, 4 is Friday, 5 is Saturday, 6 is Sunday

    # Skip sending messages on Friday (4) and Saturday (5)
    if day_of_week == 4 or day_of_week == 5:
        print(
            f"Today is {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day_of_week]}, skipping reminder")
        return

    # Send reminder and start collecting orders
    keyboard = [
        [InlineKeyboardButton("Place Order", callback_data="place_order")],
        [InlineKeyboardButton("See Current Orders", callback_data="view_orders")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=f"🍔 Time to order food! Please place your orders within {COLLECTION_TIME_MINUTES} minutes.\n"
             f"Use /order [your food request] to place an order.\n\n"
             f"Examples:\n"
             f"• /order 2x burger and fries\n"
             f"• /order chicken sandwich\n"
             f"• /order 3 tacos",
        reply_markup=reply_markup
    )

    # Update state
    order_state["is_collecting"] = True
    order_state["orders"] = {}
    order_state["collection_end_time"] = now + datetime.timedelta(minutes=COLLECTION_TIME_MINUTES)
    save_state()

    # Schedule end of collection
    context.job_queue.run_once(
        lambda ctx: asyncio.create_task(end_collection(ctx)),
        COLLECTION_TIME_MINUTES * 60
    )

    print(
        f"Reminder sent and collection started on {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day_of_week]}")


def main():
    # Load any existing state
    if os.path.exists(ORDER_STATE_FILE):
        load_state()

    # Set up the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("order", place_order))
    application.add_handler(CommandHandler("cancel", cancel_order))
    application.add_handler(CommandHandler("summary", show_summary))
    application.add_handler(CommandHandler("collect", start_collection))
    application.add_handler(CommandHandler("close", close_collection))
    application.add_handler(CommandHandler("recite", generate_receipt))

    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Get Cairo timezone
    cairo_tz = timezone("Africa/Cairo")
    now = datetime.datetime.now(cairo_tz)

    # Set reminder time
    local_reminder_time = now.replace(hour=9, minute=50, second=0, microsecond=0)

    # If time already passed today, schedule for tomorrow
    if now > local_reminder_time:
        local_reminder_time += datetime.timedelta(days=1)

    # Convert to UTC for job_queue
    utc_time = local_reminder_time.astimezone(timezone('UTC')).time()

    print(f"Scheduling food order reminder for {local_reminder_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"UTC time: {utc_time.strftime('%H:%M:%S')}")
    print("Reminders will be skipped on Fridays and Saturdays")

    # Schedule the daily job
    application.job_queue.run_daily(
        reminder_callback,
        time=utc_time
    )

    # Check periodically if collection should end
    application.job_queue.run_repeating(
        check_collection_timeout,
        interval=60,  # check every minute
        first=10  # start checking after 10 seconds
    )

    print("Food Order Bot started. Press Ctrl+C to stop.")

    # Start the bot
    application.run_polling()


if __name__ == '__main__':
    import asyncio

    main()