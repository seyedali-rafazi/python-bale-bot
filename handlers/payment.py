# handlers/payment.py

from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes
from core.database import add_vip_time, add_transaction
from dotenv import load_dotenv
import os

load_dotenv()
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
PAYMENT_VALUE = os.getenv("PAYMENT_VALUE")
VIP_LIMIT_VALUE = int(os.getenv("VIP_LIMIT_VALUE", 30))


async def btn_buy_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    title = "اشتراک VIP"
    description = f"ارتقا به حساب ویژه برای $ {VIP_LIMIT_VALUE} $ روز"
    payload = f"vip_charge_{chat_id}"
    currency = "IRR"
    prices = [LabeledPrice(f"اشتراک {VIP_LIMIT_VALUE} روزه", int(PAYMENT_VALUE))]

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter="buy_vip",
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("vip_charge_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="خطا در اطلاعات پرداخت.")


async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    chat_id = str(update.effective_chat.id)
    payment_info = update.message.successful_payment

    total_amount = payment_info.total_amount
    payload = payment_info.invoice_payload
    provider_charge_id = payment_info.provider_payment_charge_id

    add_transaction(
        user_id=chat_id,
        amount=total_amount,
        payload=payload,
        provider_charge_id=provider_charge_id,
    )

    add_vip_time(chat_id, VIP_LIMIT_VALUE)

    amount_toman = int(total_amount / 10)  # محاسبه تومان: $$ amount / 10 $$
    receipt_text = (
        "✅ **پرداخت شما با موفقیت تایید و ثبت شد!**\n\n"
        "🧾 **رسید تراکنش شما:**\n"
        f"👤 شناسه: `{chat_id}`\n"
        f"💰 مبلغ: $ {amount_toman} $ تومان\n"
        f"🔖 کد پیگیری: `{provider_charge_id}`\n\n"
        f"🌟 زمان اشتراک شما $ {VIP_LIMIT_VALUE} $ روز تمدید شد."
    )

    await update.message.reply_text(text=receipt_text, parse_mode="Markdown")
