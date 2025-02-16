import json, os, logging, uuid, requests, textwrap
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from flask import Flask, request, jsonify
from threading import Thread
from dotenv import load_dotenv

flask_app = Flask(__name__)

DATA_FILE = "users.json" # JSON file is enough I guess
load_dotenv()
TOKEN = os.getenv("TELEGRAM_API_TOKEN")

logging.basicConfig(level=logging.INFO)

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        users = json.load(f)
else:
    users = {"users": []}

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=4)

def generate_plugin_id():
    existing_ids = {user["plugin_id"] for user in users["users"]}
    while True:
        new_id = str(uuid.uuid4())
        if new_id not in existing_ids:
            return new_id

def strip_spaces(msg):
    return textwrap.dedent(msg)

async def start(update: Update, context: CallbackContext) -> None:
    telegram_id = update.message.chat_id

    for user in users["users"]:
        if user["telegram_id"] == telegram_id:
            if not user["subscribed"]:
                user["subscribed"] = True
                save_users()
                await update.message.reply_text(f"Welcome back! You resubscribed. Your UUID: `{user['plugin_id']}`", parse_mode="MarkdownV2")
            else:
                await update.message.reply_text(f"You are already registered with UUID `{user['plugin_id']}`", parse_mode="MarkdownV2")
            return

    plugin_id = generate_plugin_id()
    users["users"].append({"telegram_id": telegram_id, "plugin_id": plugin_id, "subscribed": True})
    save_users()

    await update.message.reply_text(f"Registration complete! Your UUID: `{plugin_id}`", parse_mode="MarkdownV2")

async def stop(update: Update, context: CallbackContext) -> None:
    telegram_id = update.message.chat_id

    for user in users["users"]:
        if user["telegram_id"] == telegram_id:
            user["subscribed"] = False
            save_users()
            await update.message.reply_text("You have been unsubscribed.")
            return

    await update.message.reply_text("You are not registered!")

async def help(update: Update, context: CallbackContext) -> None:
    help = """
    Available commands:
    /start - Register new UUID for your user.
    /stop - Unsubscribe from messages.
    /remove - Remove your data completely.
    /myid - Prints your UUID if it exists.
    /help - Prints this info."""
    await update.message.reply_text(strip_spaces(help))
    return

async def remove(update: Update, context: CallbackContext) -> None:
    telegram_id = update.message.chat_id

    for user in users["users"]:
        if user["telegram_id"] == telegram_id:
            users["users"].remove(user)
            save_users()
            await update.message.reply_text("You have been completely removed from the system.")
            return

    await update.message.reply_text("You are not registered, so nothing to remove!")

async def my_plugin_id(update: Update, context: CallbackContext) -> None:
    telegram_id = update.message.chat_id

    for user in users["users"]:
        if user["telegram_id"] == telegram_id:
            my_uuid = user["plugin_id"]
            formatted_msg = f"""
            *Your UUID is:*

            `{my_uuid}`
            """
            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")
            return

    await update.message.reply_text("You are not registered!")

def send_telegram_message(plugin_id, message): # Can't async this...
    for user in users["users"]:
        if user["plugin_id"] == plugin_id:
            if not user["subscribed"]:
                logging.warning(f"User with UUID {plugin_id} is unsubscribed. Message not sent.")
                return jsonify({"status": "error", "message": f"User with UUID {plugin_id} is unsubscribed."}), 400

            telegram_id = user["telegram_id"]
            try:
                url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                payload = {
                    'chat_id': telegram_id,
                    'text': message,
                    'parse_mode': "HTML"
                }
                response = requests.post(url, params=payload)

                if response.status_code == 200:
                    logging.info(f"Telegram message sent to {plugin_id}!")
                    return jsonify({"status": "success", "message": f"Message sent to {plugin_id}."}), 200
                else:
                    logging.error(f"Failed to send message to {plugin_id}. Status code: {response.status_code}")
                    return jsonify({"status": "error", "message": f"Failed to send message to {plugin_id}. Status code: {response.status_code}."}), 500
            except Exception as e:
                logging.error(f"An error occurred while sending the message: {e}")
                return jsonify({"status": "error", "message": f"An error occurred while sending the message: {e}."}), 500
    return jsonify({"status": "error", "message": "User not found."}), 404

@flask_app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    plugin_id = data.get("plugin_id")
    message = data.get("message")

    if not plugin_id or not message:
        return jsonify({"status": "error", "message": "Missing plugin_id or message."}), 400

    return send_telegram_message(plugin_id, message)

def main():
    telegram_app = Application.builder().token(TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("stop", stop))
    telegram_app.add_handler(CommandHandler("remove", remove))
    telegram_app.add_handler(CommandHandler("help", help))
    telegram_app.add_handler(CommandHandler("myid", my_plugin_id))

    # Flask thingy
    flask_thread = Thread(target=flask_app.run, kwargs={"host": "0.0.0.0", "port": 5000})
    flask_thread.daemon = True
    flask_thread.start()

    telegram_app.run_polling()

if __name__ == "__main__":
    main()
