# handlers/payment.py

from telegram import Update, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.database import add_vip_time, add_transaction, add_cloud_storage
from dotenv import load_dotenv
import os

load_dotenv()
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
PAYMENT_VALUE = os.getenv("PAYMENT_VALUE")
VIP_LIMIT_VALUE = int(os.getenv("VIP_LIMIT_VALUE", 30))

# Cloud storage package prices (in Toman - you should set these)
CLOUD_PRICES = {
    5: int(os.getenv("CLOUD_5GB_PRICE", 50000)),  # 50,000 Toman
    10: int(os.getenv("CLOUD_10GB_PRICE", 90000)),  # 90,000 Toman
    20: int(os.getenv("CLOUD_20GB_PRICE", 170000)),  # 170,000 Toman
    50: int(os.getenv("CLOUD_50GB_PRICE", 400000)),  # 400,000 Toman
}


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
    await query.answer()  # پایان حالت لودینگ دکمه

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
        if query.invoice_payload.startswith(
            "vip_charge_"
        ) or query.invoice_payload.startswith("cloud_charge_"):
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
        await add_transaction(
            user_id=chat_id,
            amount=total_amount,
            payload=payload,
            provider_charge_id=provider_charge_id,
        )

        amount_toman = int(total_amount / 10)  # محاسبه تومان

        # تشخیص نوع پرداخت از payload
        if payload.startswith("vip_charge_"):
            # ===== پرداخت VIP =====
            await add_vip_time(chat_id, VIP_LIMIT_VALUE)

            await add_cloud_storage(chat_id, 5000)

            receipt_text = (
                "✅ <b>پرداخت شما با موفقیت تایید و ثبت شد!</b>\n\n"
                "🧾 <b>رسید تراکنش شما:</b>\n"
                f"👤 شناسه: <code>{chat_id}</code>\n"
                f"💰 مبلغ: $ {amount_toman} $ تومان\n"
                f"🔖 کد پیگیری: <code>{provider_charge_id}</code>\n\n"
                f"🌟 زمان اشتراک شما $ {VIP_LIMIT_VALUE} $ روز تمدید شد."
                "☁️ <b>همچنین ۵۰۰۰ مگابایت (5GB) فضای ابری به حساب شما اضافه شد!</b>"
            )

        elif payload.startswith("cloud_charge_"):
            # ===== پرداخت حجم ابری =====
            parts = payload.split("_")
            if len(parts) >= 4:
                size_gb = int(parts[3])
            else:
                size_gb = 5

            size_mb = size_gb * 1024
            await add_cloud_storage(chat_id, size_mb)

            receipt_text = (
                "✅ <b>پرداخت شما با موفقیت تایید و ثبت شد!</b>\n\n"
                "🧾 <b>رسید تراکنش شما:</b>\n"
                f"👤 شناسه: <code>{chat_id}</code>\n"
                f"💾 حجم خریداری شده: <b>{size_gb} GB</b>\n"
                f"💰 مبلغ: $ {amount_toman} $ تومان\n"
                f"🔖 کد پیگیری: <code>{provider_charge_id}</code>\n\n"
                f"☁️ حجم ابری شما به اندازه <b>{size_gb} GB</b> افزایش یافت!"
            )
        else:
            receipt_text = "✅ <b>پرداخت موفق!</b>"

        await update.message.reply_text(text=receipt_text, parse_mode="HTML")

    except Exception as e:
        print(f"Error in payment: {e}")
        error_text = (
            "⚠️ <b>پرداخت شما انجام شد اما در ثبت سیستم مشکلی پیش آمد!</b>\n\n"
            f"کد پیگیری شما: <code>{provider_charge_id}</code>\n"
            f"شناسه شما: <code>{chat_id}</code>\n"
            "لطفاً این پیام را برای پشتیبانی ارسال کنید.\n"
            "@digiacahr_admin"
        )
        await update.message.reply_text(text=error_text, parse_mode="HTML")


async def accept_cloud_purchase_tos(
    update: Update, context: ContextTypes.DEFAULT_TYPE, size_gb: int
):
    """Handle TOS acceptance for cloud storage purchase and proceed to payment"""
    query = update.callback_query

    try:
        await query.answer()  # Try to answer, but don't fail if it's too old
    except Exception as e:
        print(f"Note: Could not answer callback query (may be too old): {e}")

    chat_id = update.effective_chat.id

    # Get price for selected size
    price_toman = CLOUD_PRICES.get(size_gb, CLOUD_PRICES[5])
    price_rial = price_toman * 10  # Convert to Rial

    try:
        # Try to delete previous message
        await query.message.delete()
    except Exception as e:
        print(f"Note: Could not delete message: {e}")

    title = f"خریدگاه حجم ابری - {size_gb} GB"
    description = f"افزایش حجم ذخیره‌سازی ابری به میزان {size_gb} GB"
    payload = f"cloud_charge_{chat_id}_{size_gb}"
    currency = "IRR"
    prices = [LabeledPrice(f"{size_gb} GB حجم ابری", price_rial)]

    # Send invoice for cloud storage purchase
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter=f"buy_cloud_{size_gb}gb",
    )


# All payments (VIP and Cloud) are now handled in successful_payment_callback above
