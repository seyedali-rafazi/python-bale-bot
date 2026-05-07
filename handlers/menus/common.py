from telegram import Update
from telegram.ext import ContextTypes
from handlers.commands import cmd_start


async def btn_back_action(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await cmd_start(update, context)
