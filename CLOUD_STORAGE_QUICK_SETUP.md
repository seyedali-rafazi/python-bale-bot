# Cloud Storage - Quick Integration Snippets

## 1. Add to imports in main.py

```python
# Cloud storage functionality
from handlers.menus.cloud import (
    btn_cloud_storage_menu,
    btn_buy_cloud_menu,
    btn_cloud_files,
    btn_buy_cloud_size,
)
from handlers.states.state_cloud import (
    start_cloud_upload,
    handle_cloud_file_upload,
    cancel_cloud_upload,
    WAIT_FOR_FILE,
)
from core.constants import BTN_CLOUD_STORAGE, BTN_UPLOAD_TO_CLOUD
import re
```

## 2. Register handlers (add to your handler setup in main.py)

### Message Handlers Block:
```python
# === CLOUD STORAGE HANDLERS ===
app.add_handler(MessageHandler(Filters.text(BTN_CLOUD_STORAGE), btn_cloud_storage_menu))

# Cloud upload conversation
cloud_conv = ConversationHandler(
    entry_points=[MessageHandler(Filters.text(BTN_UPLOAD_TO_CLOUD), start_cloud_upload)],
    states={WAIT_FOR_FILE: [MessageHandler(Filters.document | Filters.video | Filters.audio | Filters.photo, handle_cloud_file_upload)]},
    fallbacks=[CommandHandler("cancel", cancel_cloud_upload)],
)
app.add_handler(cloud_conv)
```

### Callback Query Handlers Block:
```python
# === CLOUD STORAGE CALLBACKS ===
# Cloud menu navigation
app.add_handler(CallbackQueryHandler(btn_cloud_storage_menu, pattern="^cloud_storage$"))
app.add_handler(CallbackQueryHandler(btn_buy_cloud_menu, pattern="^cloud_buy_menu$|^cloud_back$"))
app.add_handler(CallbackQueryHandler(btn_cloud_files, pattern="^cloud_files$"))

# Package selection - create wrapper functions
async def handle_cloud_5gb(u, c): await btn_buy_cloud_size(u, c, 5)
async def handle_cloud_10gb(u, c): await btn_buy_cloud_size(u, c, 10)
async def handle_cloud_20gb(u, c): await btn_buy_cloud_size(u, c, 20)
async def handle_cloud_50gb(u, c): await btn_buy_cloud_size(u, c, 50)

app.add_handler(CallbackQueryHandler(handle_cloud_5gb, pattern="^cloud_buy_5gb$"))
app.add_handler(CallbackQueryHandler(handle_cloud_10gb, pattern="^cloud_buy_10gb$"))
app.add_handler(CallbackQueryHandler(handle_cloud_20gb, pattern="^cloud_buy_20gb$"))
app.add_handler(CallbackQueryHandler(handle_cloud_50gb, pattern="^cloud_buy_50gb$"))

# Purchase TOS acceptance
async def handle_cloud_tos(update, context):
    match = re.search(r'(\d+)', update.callback_query.data)
    if match:
        size = int(match.group(1))
        await accept_cloud_purchase_tos(update, context, size)

app.add_handler(CallbackQueryHandler(handle_cloud_tos, pattern=r"^accept_cloud_purchase_\d+$"))
```

## 3. Update successful_payment_callback

Replace the entire successful_payment_callback function with:

```python
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    payment_info = update.message.successful_payment
    
    total_amount = payment_info.total_amount
    payload = payment_info.invoice_payload
    provider_charge_id = payment_info.provider_payment_charge_id

    try:
        # Add transaction record
        await add_transaction(user_id=chat_id, amount=total_amount, payload=payload, provider_charge_id=provider_charge_id)
        
        # Determine payment type from payload
        if payload.startswith("vip_charge_"):
            # ===== VIP PAYMENT =====
            await add_vip_time(chat_id, VIP_LIMIT_VALUE)
            amount_toman = int(total_amount / 10)
            receipt_text = (
                "✅ <b>پرداخت شما با موفقیت تایید و ثبت شد!</b>\n\n"
                "🧾 <b>رسید تراکنش شما:</b>\n"
                f"👤 شناسه: <code>{chat_id}</code>\n"
                f"💰 مبلغ: $ {amount_toman} $ تومان\n"
                f"🔖 کد پیگیری: <code>{provider_charge_id}</code>\n\n"
                f"🌟 زمان اشتراک شما $ {VIP_LIMIT_VALUE} $ روز تمدید شد."
            )
            
        elif payload.startswith("cloud_charge_"):
            # ===== CLOUD PAYMENT =====
            parts = payload.split("_")
            size_gb = int(parts[3]) if len(parts) >= 4 else 5
            size_mb = size_gb * 1024
            
            from core.database import add_cloud_storage
            await add_cloud_storage(chat_id, size_mb)
            
            amount_toman = int(total_amount / 10)
            receipt_text = (
                "✅ <b>پرداخت شما با موفقیت تایید و ثبت شد!</b>\n\n"
                "🧾 <b>رسید تراکنش شما:</b>\n"
                f"👤 شناسه: <code>{chat_id}</code>\n"
                f"💾 حجم خریداری شده: <b>{size_gb} GB</b>\n"
                f"💰 مبلغ: $ {amount_toman} $ تومان\n"
                f"🔖 کد پیگیری: <code>{provider_charge_id}</code>\n\n"
                f"☁️ حجم ابری شما به اندازه **{size_gb} GB** افزایش یافت!"
            )
        
        else:
            receipt_text = "✅ <b>پرداخت موفق!</b>"
        
        await update.message.reply_text(text=receipt_text, parse_mode="HTML")

    except Exception as e:
        print(f"Payment error: {e}")
        error_text = (
            "⚠️ <b>پرداخت شما انجام شد اما در ثبت سیستم مشکلی پیش آمد!</b>\n\n"
            f"کد پیگیری: <code>{provider_charge_id}</code>\n"
            f"شناسه: <code>{chat_id}</code>\n"
            "لطفاً این پیام را برای پشتیبانی ارسال کنید.\n@digiacahr_admin"
        )
        await update.message.reply_text(text=error_text, parse_mode="HTML")
```

## 4. Update precheckout_callback

Replace existing function with:

```python
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    try:
        if query.invoice_payload.startswith(("vip_charge_", "cloud_charge_")):
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message="❌ خطا در اطلاعات پرداخت. لطفاً دوباره تلاش کنید.")
    except Exception as e:
        await query.answer(ok=False, error_message="❌ مشکلی در ارتباط با درگاه پیش آمد.")
```

## 5. Add to .env file

```
# Cloud Storage Pricing (Toman)
CLOUD_5GB_PRICE=50000
CLOUD_10GB_PRICE=90000
CLOUD_20GB_PRICE=170000
CLOUD_50GB_PRICE=400000
```

## 6. Import needed in payment.py

Make sure payment.py has this import:
```python
from core.database import add_vip_time, add_transaction, add_cloud_storage
```

## Key Points

- **Order matters**: Register cloud handlers BEFORE user text handlers
- **File types**: Support document, video, audio, photo uploads
- **Storage**: 1 GB = 1024 MB in calculations
- **Prices**: In .env are Toman (×10 = Rial for payment gateway)
- **Callbacks**: Patterns must be unique and specific
- **Database**: Tables created automatically on bot startup via init_db()

## Testing Single Feature

To test just cloud upload:
```python
# In your test script
from handlers.states.state_cloud import start_cloud_upload

# Simulate message
await start_cloud_upload(update, context)
```

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "Button not appearing" | Rebuild keyboard with `get_main_menu_keyboard()` after reload |
| "Upload fails" | Check S3 credentials in .env; check available disk space |
| "Payment error" | Verify PROVIDER_TOKEN is set; check CLOUD_*_PRICE in .env |
| "File not tracked" | Check database initialized; verify cloud_files table exists |
| "Download link invalid" | S3 links expire after 3 hours; regenerate upload |

