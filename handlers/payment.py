# handlers/payment.py


from telegram import Update, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.database import add_vip_time, add_transaction
from dotenv import load_dotenv
import os

load_dotenv()
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
PAYMENT_VALUE = os.getenv("PAYMENT_VALUE")
VIP_LIMIT_VALUE = int(os.getenv("VIP_LIMIT_VALUE", 30))


async def btn_buy_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # متن موافقت‌نامه
    tos_text = f"""
📋 **قوانین و مقررات خرید اشتراک ویژه (VIP)**

کاربر گرامی، با ارتقا به حساب ویژه، شما از امکانات زیر بهره‌مند می‌شوید:
🚀 **صف دانلود جداگانه و اختصاصی** (بدون معطلی)
☁️ **قابلیت آپلود مستقیم در سرور ابری**
📈 **افزایش چشمگیر محدودیت‌های روزانه** به شرح زیر:
🎥 یوتیوب: $20$ درخواست در روز
🔍 اکسپلور تیک‌تاک: $10$ درخواست در روز
📥 دانلود از تیک‌تاک: $10$ درخواست در روز
📌 پینترست: $30$ درخواست در روز
🎧 موسیقی: $20$ درخواست در روز

⚠️ **لطفاً پیش از پرداخت به نکات زیر توجه فرمایید:**
۱. مبالغ تعیین‌شده صرفاً جهت تأمین هزینه‌های نگهداری سرورها می‌باشد؛ لذا **وجه پرداختی به هیچ عنوان قابل استرداد (بازگشت) نیست**.
۲. لطفاً از جستجو، دانلود و ارسال **محتوای حساس و مغایر با قوانین پیام‌رسان بله** اکیداً خودداری فرمایید. مسئولیت استفاده نادرست مستقیماً بر عهده کاربر می‌باشد.

جهت تایید قوانین و انتقال به درگاه پرداخت، دکمه زیر را لمس کنید. 👇
"""
    # دکمه شیشه‌ای پذیرش
    keyboard = [
        [InlineKeyboardButton("✅ پذیرش قوانین و پرداخت", callback_data="accept_tos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        tos_text, reply_markup=reply_markup, parse_mode="Markdown"
    )


# این تابع زمانی فراخوانی می‌شود که کاربر دکمه پذیرش را می‌زند
async def handle_tos_acceptance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # پایان حالت لودینگ دکمه به همراه مدیریت خطا
    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    chat_id = update.effective_chat.id

    # (اختیاری) حذف پیام قوانین برای خلوت شدن صفحه
    await query.message.delete()

    title = "اشتراک VIP"
    description = f"ارتقا به حساب ویژه برای $ {VIP_LIMIT_VALUE} $ روز"
    payload = f"vip_charge_{chat_id}"
    currency = "IRR"
    prices = [LabeledPrice(f"اشتراک $ {VIP_LIMIT_VALUE} $ روزه", int(PAYMENT_VALUE))]

    # ارسال فاکتور پرداخت (درگاه)
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
    try:
        # بررسی صحت اطلاعات ارسالی پیش از کسر وجه
        if query.invoice_payload.startswith("vip_charge_"):
            await query.answer(ok=True)
        else:
            await query.answer(
                ok=False,
                error_message="❌ خطا در اطلاعات پرداخت. لطفاً دوباره تلاش کنید.",
            )
    except Exception as e:
        # نمایش خطای پاپ‌آپ در صورت مشکل در اتصال به درگاه
        await query.answer(
            ok=False,
            error_message="❌ مشکلی در ارتباط با درگاه پیش آمد. تراکنش انجام نشد.",
        )


async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    chat_id = str(update.effective_chat.id)
    payment_info = update.message.successful_payment

    total_amount = payment_info.total_amount
    payload = payment_info.invoice_payload
    provider_charge_id = payment_info.provider_payment_charge_id

    try:
        # ثبت تراکنش در دیتابیس
        add_transaction(
            user_id=chat_id,
            amount=total_amount,
            payload=payload,
            provider_charge_id=provider_charge_id,
        )

        # افزایش زمان VIP کاربر
        add_vip_time(chat_id, VIP_LIMIT_VALUE)

        amount_toman = int(total_amount / 10)  # محاسبه تومان

        # استفاده از HTML به جای Markdown برای جلوگیری از کرش کردن ارسال پیام
        receipt_text = (
            "✅ <b>پرداخت شما با موفقیت تایید و ثبت شد!</b>\n\n"
            "🧾 <b>رسید تراکنش شما:</b>\n"
            f"👤 شناسه: <code>{chat_id}</code>\n"
            f"💰 مبلغ: $ {amount_toman} $ تومان\n"
            f"🔖 کد پیگیری: <code>{provider_charge_id}</code>\n\n"
            f"🌟 زمان اشتراک شما $ {VIP_LIMIT_VALUE} $ روز تمدید شد."
        )

        await update.message.reply_text(text=receipt_text, parse_mode="HTML")

    except Exception as e:
        # در صورتی که بعد از پرداخت موفق خطایی رخ دهد (مثلا در دیتابیس)
        error_text = (
            "⚠️ <b>پرداخت شما انجام شد اما در ثبت سیستم مشکلی پیش آمد!</b>\n\n"
            f"کد پیگیری شما: <code>{provider_charge_id}</code>\n"
            f" شناشه شما: <code>{chat_id}</code>\n"
            "لطفاً این پیام را برای پشتیبانی ارسال کنید تا اشتراک شما دستی فعال شود."
            "@digiacahr_admin"
        )
        await update.message.reply_text(text=error_text, parse_mode="HTML")
