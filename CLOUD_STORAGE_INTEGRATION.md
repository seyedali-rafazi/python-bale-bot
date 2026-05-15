# Cloud Storage Feature - Integration Guide

## Overview

I've implemented a complete cloud storage system for your bot with the following components:

```
┌─────────────────────────────────────────────────────────────┐
│                    CLOUD STORAGE SYSTEM                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User buys VIP → Gets 5000 MB cloud storage                 │
│           ↓                                                  │
│  Uploads file (500 MB) → Storage becomes 4500 MB            │
│           ↓                                                  │
│  Gets download link → File tracked in database              │
│                                                              │
│  User wants more → Clicks "خرید حجم ابری 🌟"              │
│           ↓                                                  │
│  Selects package (5/10/20/50 GB) → Payment processed        │
│           ↓                                                  │
│  Payment successful → Storage increased accordingly          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## What Was Created

### 1. **Database Layer** (`core/database/cloud.py`)
Functions to manage cloud storage:
- `get_user_cloud_info()` - Get user's total and used storage
- `get_available_cloud_mb()` - Get free space
- `add_cloud_storage()` - Increase quota (after purchase)
- `reduce_cloud_storage()` - Decrease quota (when uploading)
- `add_cloud_file()` - Track uploaded file
- `get_user_cloud_files()` - List user's files
- `delete_cloud_file()` - Remove file and free space
- `get_cloud_usage_stats()` - Get detailed statistics

### 2. **UI/Menu Layer** (`handlers/menus/cloud.py`)
User interface functions:
- `btn_cloud_storage_menu()` - Main cloud menu with stats
- `btn_buy_cloud_menu()` - Package selection menu
- `btn_cloud_files()` - Show uploaded files
- `btn_buy_cloud_size()` - Handle purchase with TOS

### 3. **File Upload Handler** (`handlers/states/state_cloud.py`)
Conversation handler for file uploads:
- `start_cloud_upload()` - Initialize upload
- `handle_cloud_file_upload()` - Process file and upload to S3
- `cancel_cloud_upload()` - Cancel operation

### 4. **Payment Integration** (`handlers/payment.py`)
New payment functions:
- `accept_cloud_purchase_tos()` - Show TOS and proceed to payment
- `handle_cloud_precheckout()` - Validate payment
- `successful_cloud_payment_callback()` - Process successful payment

### 5. **Database Schema Updates** (`core/database/init_db.py`)
New columns and tables:
```sql
-- Users table additions
ALTER TABLE users ADD COLUMN cloud_total_mb INTEGER DEFAULT 5000;
ALTER TABLE users ADD COLUMN cloud_used_mb INTEGER DEFAULT 0;

-- New table for tracking files
CREATE TABLE cloud_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    file_name TEXT,
    file_size_mb INTEGER,
    download_link TEXT,
    upload_date TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### 6. **UI Constants** (`core/constants.py`)
```python
BTN_CLOUD_STORAGE = "☁️ ذخیره ابری"
BTN_BUY_CLOUD = "خرید حجم ابری 🌟"
BTN_BUY_CLOUD_SIZE1 = "خرید  5GB حجم ابری 🌟"
BTN_BUY_CLOUD_SIZE2 = "خرید  10GB حجم ابری 🌟"
BTN_BUY_CLOUD_SIZE3 = "خرید  20GB حجم ابری 🌟"
BTN_BUY_CLOUD_SIZE4 = "خرید 50GB حجم ابری 🌟"
BTN_UPLOAD_TO_CLOUD = "📤 آپلود فایل"
BTN_CLOUD_FILES = "📂 فایل‌های من"
```

## Integration Steps

### Step 1: Update main.py - Add imports

```python
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
from handlers.payment import (
    accept_cloud_purchase_tos,
    successful_cloud_payment_callback,
)
from core.constants import BTN_CLOUD_STORAGE, BTN_UPLOAD_TO_CLOUD
import re
```

### Step 2: Update successful_payment_callback in payment.py

The `successful_payment_callback` function now needs to handle both VIP and Cloud purchases:

```python
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    payment_info = update.message.successful_payment
    payload = payment_info.invoice_payload
    
    # Check if it's a VIP or Cloud charge
    if payload.startswith("vip_charge_"):
        # Handle VIP payment
        await handle_vip_payment(update, context)
    elif payload.startswith("cloud_charge_"):
        # Handle Cloud payment
        await successful_cloud_payment_callback(update, context)
```

### Step 3: Add message handlers in main.py

```python
# Add to your handler setup (around line where other message handlers are)

# Cloud storage main menu
app.add_handler(MessageHandler(Filters.text(BTN_CLOUD_STORAGE), btn_cloud_storage_menu))

# Cloud file upload conversation
cloud_upload_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(Filters.text(BTN_UPLOAD_TO_CLOUD), start_cloud_upload)
    ],
    states={
        WAIT_FOR_FILE: [
            MessageHandler(
                Filters.document | Filters.video | Filters.audio | Filters.photo,
                handle_cloud_file_upload
            ),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_cloud_upload)],
)
app.add_handler(cloud_upload_conv_handler)
```

### Step 4: Add callback handlers in main.py

```python
# Cloud storage callbacks
app.add_handler(CallbackQueryHandler(
    lambda u, c: btn_cloud_storage_menu(u, c),
    pattern="^cloud_storage$"
))

app.add_handler(CallbackQueryHandler(
    btn_buy_cloud_menu,
    pattern="^cloud_buy_menu$|^cloud_back$"
))

app.add_handler(CallbackQueryHandler(
    btn_cloud_files,
    pattern="^cloud_files$"
))

# Cloud purchase handlers
async def handle_cloud_5gb(update, context):
    await btn_buy_cloud_size(update, context, 5)

async def handle_cloud_10gb(update, context):
    await btn_buy_cloud_size(update, context, 10)

async def handle_cloud_20gb(update, context):
    await btn_buy_cloud_size(update, context, 20)

async def handle_cloud_50gb(update, context):
    await btn_buy_cloud_size(update, context, 50)

app.add_handler(CallbackQueryHandler(handle_cloud_5gb, pattern="^cloud_buy_5gb$"))
app.add_handler(CallbackQueryHandler(handle_cloud_10gb, pattern="^cloud_buy_10gb$"))
app.add_handler(CallbackQueryHandler(handle_cloud_20gb, pattern="^cloud_buy_20gb$"))
app.add_handler(CallbackQueryHandler(handle_cloud_50gb, pattern="^cloud_buy_50gb$"))

# Cloud purchase TOS acceptance
async def handle_cloud_purchase_tos(update, context):
    match = re.search(r'accept_cloud_purchase_(\d+)', update.callback_query.data)
    if match:
        size_gb = int(match.group(1))
        await accept_cloud_purchase_tos(update, context, size_gb)

app.add_handler(CallbackQueryHandler(
    handle_cloud_purchase_tos,
    pattern=r"^accept_cloud_purchase_\d+$"
))
```

### Step 5: Update .env file

Add cloud storage pricing:

```
# Cloud Storage Pricing (in Toman)
CLOUD_5GB_PRICE=50000
CLOUD_10GB_PRICE=90000
CLOUD_20GB_PRICE=170000
CLOUD_50GB_PRICE=400000
```

## User Flow

```
1. User clicks "☁️ ذخیره ابری" button
   ↓
2. Shows cloud menu with:
   - Current storage usage (visual bar)
   - File count
   - Used/Total GB
   - Options: Upload, View Files, Buy More
   ↓
3. Upload option:
   - User sends file (document, video, audio, photo)
   - File size checked against available space
   - Uploaded to S3 cloud
   - Storage reduced automatically
   - Download link generated
   ↓
4. Buy option:
   - Shows 4 packages (5/10/20/50 GB)
   - User selects package
   - TOS shown
   - Payment processed
   - Storage increased after payment
   ↓
5. View Files option:
   - Lists all uploaded files
   - Shows file size and upload date
   - Download links available
```

## Important Notes

1. **Storage Calculation**: 1 GB = 1024 MB
   - Each user starts with 5000 MB (5 GB)
   - File size is deducted when uploaded
   - Package purchases add to total quota

2. **Payment Processing**:
   - Payload format: `cloud_charge_{user_id}_{size_gb}`
   - Prices in .env are in Toman
   - Converted to Rial internally (×10)

3. **S3 Integration**:
   - Uses existing `upload_to_s3()` from `services/parspack_s3.py`
   - Download links valid for 3 hours
   - Temporary files cleaned up after upload

4. **Database**:
   - All new users automatically get 5000 MB
   - Existing users need migration (or set manually)
   - Cloud files table tracks all uploads
   - Storage stats calculated in real-time

5. **Error Handling**:
   - File size validation before upload
   - Insufficient space checks
   - S3 upload failure handling
   - Payment validation

## Testing Checklist

- [ ] Database initialized with new tables/columns
- [ ] Cloud storage menu displays correctly
- [ ] Upload shows available space
- [ ] File upload to S3 works
- [ ] Storage reduced after upload
- [ ] Download link generated
- [ ] Files list shows correctly
- [ ] Purchase menu displays 4 packages
- [ ] Payment TOS shown before checkout
- [ ] Payment processing works
- [ ] Storage increased after payment
- [ ] VIP payment still works (shouldn't break)

## Support

If integration issues occur, check:
1. All imports are added to main.py
2. Handlers registered in correct order
3. Environment variables set
4. Database migration ran
5. S3 credentials valid
