# core/admin.py


from telegram import Update
from telegram.ext import ContextTypes
from core.database import (
    get_db,
    get_total_users,
    set_vip,
    get_all_users,
    get_users_batch,
    get_total_vip_users,
    reset_user_limits,
    add_vip_time_to_all,
    set_vip_expire_date,
    get_full_user_info,
    give_5gb_to_existing_vips,
    add_cloud_storage,
    get_user_cloud_info,
)
import os
import logging
from dotenv import load_dotenv
import asyncio
import aiosqlite
from core.database import DB_NAME
from core.database import get_setting, set_setting
from core.database.yt_blacklist import (
    add_channel_blacklist,
    remove_channel_blacklist,
    list_channel_blacklist,
    add_blocked_word,
    remove_blocked_word,
    list_blocked_words,
)
from core.database.youtube import (
    count_cache_needing_metadata,
    backfill_youtube_cache_metadata,
    count_incomplete_cache_rows,
    purge_incomplete_youtube_cache,
    purge_all_youtube_cache,
    drop_legacy_user_youtube_archive_table,
)
from datetime import datetime


load_dotenv()
logger = logging.getLogger(__name__)
# آیدی عددی ادمین را در فایل .env قرار دهید
ADMIN_ID = os.getenv("ADMIN_ID")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    total_users = await get_total_users()
    vip_users = await get_total_vip_users()
    normal_users = total_users - vip_users

    await update.message.reply_text(
        f"📊 **آمار ربات:**\n\n"
        f"تعداد کل کاربران: $ {total_users} $ نفر\n"
        f"کاربران عادی: $ {normal_users} $ نفر\n"
        f"کاربران VIP: $ {vip_users} $ نفر"
    )


async def cmd_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/setvip 123456789 1` برای فعال کردن\n`/setvip 123456789 0` برای غیرفعال کردن"
        )
        return

    target_user = context.args[0]
    status = int(context.args[1])

    await set_vip(target_user, status)
    status_text = "VIP شد 🌟" if status == 1 else "از VIP خارج شد ❌"

    await update.message.reply_text(f"✅ کاربر {target_user} {status_text}")


async def cmd_setexpire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n"
            "`/setexpire 123456789 27` - مجوز VIP برای 27 روز دیگر"
        )
        return

    target_user = context.args[0]
    try:
        days = int(context.args[1])
        if days < 1:
            await update.message.reply_text("❌ تعداد روز باید بیشتر از صفر باشد.")
            return
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح برای روز‌ها وارد کنید.")
        return

    success, expire_dt = await set_vip_expire_date(target_user, days)

    if success:
        await update.message.reply_text(
            f"✅ کاربر {target_user} VIP برای {days} روز دیگر شد.\n"
            f"تاریخ انقضا: {expire_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        await update.message.reply_text("❌ خطا در تنظیم VIP.")


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/userinfo 123456789`"
        )
        return

    target_user = context.args[0]
    user_data = await get_full_user_info(target_user)

    if not user_data:
        await update.message.reply_text(f"❌ کاربر {target_user} یافت نشد.")
        return

    # Parse the data
    (
        user_id,
        username,
        is_vip,
        join_date,
        vip_expire_date,
        yt_count,
        yt_date,
        music_count,
        music_date,
        pinterest_count,
        pinterest_date,
        tt_dl_count,
        tt_dl_date,
        gh_count,
        gh_date,
    ) = user_data

    # Format VIP status
    vip_status = "✅ VIP" if is_vip == 1 else "❌ عادی"

    # Format expire date
    if vip_expire_date:
        try:
            expire_dt = datetime.fromisoformat(vip_expire_date)
            now = datetime.now()
            if expire_dt > now:
                remaining = (expire_dt - now).days
                expire_text = f"{expire_dt.strftime('%Y-%m-%d %H:%M:%S')}\n({remaining} روز باقی مانده)"
            else:
                expire_text = f"{expire_dt.strftime('%Y-%m-%d %H:%M:%S')}\n(منقضی شده)"
        except:
            expire_text = vip_expire_date
    else:
        expire_text = "بدون تاریخ انقضا"

    info_text = f"""
📋 **اطلاعات کاربر {target_user}**

👤 نام کاربری: {username if username else "تعیین نشده"}
📱 شناسه: {user_id}
🎯 وضعیت: {vip_status}
📅 تاریخ انقضای VIP: {expire_text}
📝 تاریخ عضویت: {join_date if join_date else "نامشخص"}

📊 **آمار استفاده:**

🎬 یوتیوب:
   ├─ دانلود‌ها: {yt_count}
   └─ آخرین استفاده: {yt_date if yt_date else "هرگز"}

🎵 موسیقی:
   ├─ دانلود‌ها: {music_count}
   └─ آخرین استفاده: {music_date if music_date else "هرگز"}

📌 Pinterest:
   ├─ دانلود‌ها: {pinterest_count}
   └─ آخرین استفاده: {pinterest_date if pinterest_date else "هرگز"}

🎭 TikTok:
   ├─ دانلود‌ها: {tt_dl_count}
   └─ آخرین استفاده: {tt_dl_date if tt_dl_date else "هرگز"}

💻 GitHub:
   ├─ دانلود‌ها: {gh_count}
   └─ آخرین استفاده: {gh_date if gh_date else "هرگز"}
"""

    await update.message.reply_text(info_text)


_broadcast_task: asyncio.Task | None = None
_broadcast_lock = asyncio.Lock()


def is_broadcast_running() -> bool:
    return _broadcast_task is not None and not _broadcast_task.done()


async def stop_broadcast():
    global _broadcast_task
    if _broadcast_task is not None and not _broadcast_task.done():
        logger.info("Cancelling ongoing admin broadcast on shutdown...")
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error awaiting broadcast cancellation: %s", e)
    _broadcast_task = None


async def _run_broadcast_job(bot, admin_chat_id: str, message_text: str, total_users: int):
    success = 0
    fail = 0
    processed = 0
    batch_size = 50
    last_user_id: str | None = None

    logger.info("Admin broadcast started for %s users", total_users)

    try:
        while True:
            users_batch = await get_users_batch(after_user_id=last_user_id, limit=batch_size)
            if not users_batch:
                break

            for user_id in users_batch:
                last_user_id = user_id
                processed += 1

                try:
                    await bot.send_message(chat_id=user_id, text=message_text)
                    success += 1
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    fail += 1
                    logger.debug("Broadcast send error for user %s: %s", user_id, e)

                # Rate limit protection: 0.05s interval keeps load well within limits
                await asyncio.sleep(0.05)

            if processed % 200 == 0 or processed == total_users:
                logger.info("Broadcast progress: %d/%d (ok=%d, fail=%d)", processed, total_users, success, fail)

        # Notify admin of completion
        summary_text = (
            f"✅ ارسال همگانی به پایان رسید!\n\n"
            f"👥 کل مخاطبان: {total_users}\n"
            f"📨 پردازش شده: {processed}\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {fail}"
        )
        try:
            await bot.send_message(chat_id=admin_chat_id, text=summary_text)
        except Exception:
            pass

    except asyncio.CancelledError:
        logger.info("Broadcast task cancelled: processed=%d, success=%d, fail=%d", processed, success, fail)
        try:
            await bot.send_message(
                chat_id=admin_chat_id,
                text=f"⚠️ ارسال همگانی متوقف شد.\nپردازش شده: {processed} (موفق: {success}، ناموفق: {fail})",
            )
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("Unexpected error in broadcast task: %s", e)
        try:
            await bot.send_message(
                chat_id=admin_chat_id,
                text=f"❌ خطای غیرمنتظره در ارسال همگانی: {e}",
            )
        except Exception:
            pass


async def cmd_messageuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _broadcast_task
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    text = update.message.text
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "❌ متن پیام را وارد کنید.\nمثال:\n`/messageuser سلام کاربران عزیز`"
        )
        return

    message_text = parts[1]

    async with _broadcast_lock:
        if is_broadcast_running():
            await update.message.reply_text(
                "⚠️ یک ارسال همگانی در حال حاضر در حال اجرا است. لطفاً تا اتمام آن منتظر بمانید."
            )
            return

        total_users = await get_total_users()
        if total_users == 0:
            await update.message.reply_text("❌ هیچ کاربری در دیتابیس یافت نشد.")
            return

        await update.message.reply_text(
            f"⏳ ارسال همگانی در پس‌زمینه آغاز شد.\nتعداد کل کاربران: {total_users}\nگزارش پایان ارسال برای شما ارسال خواهد شد."
        )

        _broadcast_task = asyncio.create_task(
            _run_broadcast_job(
                bot=context.bot,
                admin_chat_id=chat_id,
                message_text=message_text,
                total_users=total_users,
            )
        )


async def cmd_reset_limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    conn = await get_db()
    # صفر کردن تعداد دفعات استفاده برای همه کاربران
    await conn.execute(
        "UPDATE users SET yt_count = 0, music_count = 0, pinterest_count = 0"
    )
    await conn.commit()

    await update.message.reply_text("✅ محدودیت‌های تمامی کاربران با موفقیت ریست شد.")


async def cmd_toggle_yt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    # دریافت وضعیت فعلی
    current_status = await get_setting("youtube_enabled", "1")

    # تغییر وضعیت
    new_status = "0" if current_status == "1" else "1"
    await set_setting("youtube_enabled", new_status)

    status_text = "فعال ✅" if new_status == "1" else "غیرفعال ❌"
    await update.message.reply_text(f"وضعیت دانلودر یوتیوب: {status_text}")


async def cmd_resetuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/resetuser 123456789`"
        )
        return

    target_user = context.args[0]

    await reset_user_limits(target_user)

    await update.message.reply_text(
        f"✅ محدودیت‌های کاربر $ {target_user} $ با موفقیت ریست شد."
    )


async def cmd_addvip_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال برای اضافه کردن ۵ روز:\n`/addvipall 5`"
        )
        return

    try:
        days = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح وارد کنید.")
        return

    updated_users = await add_vip_time_to_all(days)
    await update.message.reply_text(
        f"✅ با موفقیت $ {days} $ روز به اشتراک $ {updated_users} $ کاربر ویژه (پرو) اضافه شد."
    )


async def cmd_clean_yt_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    mode = (context.args[0] if context.args else "unknown").lower()

    if mode == "all":
        total = await purge_all_youtube_cache()
        await drop_legacy_user_youtube_archive_table()
        await update.message.reply_text(
            f"✅ کل کش یوتیوب پاک شد.\n"
            f"• حذف شده از `youtube_cache`: **{total}**\n"
            f"• جدول قدیمی `user_youtube_archive` هم حذف شد.\n\n"
            f"از این به بعد فقط ویدیوهای جدید با نام کانال واقعی ذخیره می‌شوند."
        )
        return

    await drop_legacy_user_youtube_archive_table()
    pending = await count_incomplete_cache_rows()
    removed = await purge_incomplete_youtube_cache()
    left = await count_incomplete_cache_rows()
    await update.message.reply_text(
        f"✅ پاکسازی ردیف‌های ناشناس / ناقص:\n"
        f"• حذف شده: **{removed}** (از **{pending}** مورد ناقص)\n"
        f"• باقی‌مانده ناقص: **{left}**\n\n"
        f"برای پاک کردن **همه** کش: `/cleanytcache all`"
    )


async def cmd_fix_yt_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    limit = 500
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ limit باید عدد باشد. مثال: `/fixytcache 1000`")
            return

    pending = await count_cache_needing_metadata()
    await update.message.reply_text(
        f"⏳ بروزرسانی نام کانال و عنوان ویدیوها...\n"
        f"در صف: **{pending}** — حداکثر **{limit}** مورد در این اجرا."
    )

    try:
        result = await backfill_youtube_cache_metadata(
            batch_size=40,
            max_total=limit,
            delay_sec=0.35,
        )
        still = await count_cache_needing_metadata()
        await update.message.reply_text(
            f"✅ پایان بروزرسانی کش یوتیوب:\n"
            f"• موفق: {result['fixed']}\n"
            f"• ناموفق: {result['failed']}\n"
            f"• پردازش‌شده: {result['processed']}\n"
            f"• باقی‌مانده در صف: {still}\n\n"
            f"اگر هنوز موردی مانده، دوباره `/fixytcache {limit}` بزنید."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")


async def cmd_addcloud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/addcloud 123456789 5000`"
        )
        return

    target_user = context.args[0]
    try:
        size_mb = int(context.args[1])
        if size_mb < 1:
            await update.message.reply_text("❌ حجم باید بیشتر از صفر باشد.")
            return
    except ValueError:
        await update.message.reply_text(
            "❌ لطفاً یک عدد صحیح برای حجم (مگابایت) وارد کنید."
        )
        return

    if not await get_full_user_info(target_user):
        await update.message.reply_text(f"❌ کاربر {target_user} یافت نشد.")
        return

    cloud_info = await get_user_cloud_info(target_user)
    old_total = (cloud_info or {}).get("total_mb") or 0
    old_used = (cloud_info or {}).get("used_mb") or 0
    old_available = old_total - old_used

    await add_cloud_storage(target_user, size_mb)

    new_total = old_total + size_mb
    new_available = new_total - old_used

    await update.message.reply_text(
        f"✅ {size_mb} مگابایت به کاربر {target_user} اضافه شد.\n\n"
        f"☁️ حجم کل: {old_total} → {new_total} MB\n"
        f"📦 مصرف شده: {old_used} MB\n"
        f"💾 فضای آزاد: {old_available} → {new_available} MB"
    )


async def cmd_give_5gb_vips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    await update.message.reply_text(
        "⏳ در حال بررسی و اعمال حجم ابری برای کاربران VIP..."
    )

    try:
        await give_5gb_to_existing_vips()
        await update.message.reply_text(
            "✅ ۵۰۰۰ مگابایت فضای ابری با موفقیت به کاربران VIP قدیمی که حجم نداشتند اضافه شد."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطایی رخ داد:\n`{str(e)}`")


async def cmd_channel_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "📋 **بلک‌لیست کانال یوتیوب**\n\n"
            "`/channelblacklist نامکانال` — افزودن\n"
            "`/channelblacklist remove نامکانال` — حذف\n"
            "`/channelblacklist list` — لیست"
        )
        return

    action = args[0].lower()
    if action == "list":
        rows = await list_channel_blacklist()
        if not rows:
            await update.message.reply_text("📭 بلک‌لیست کانال خالی است.")
            return
        lines = ["🚫 **کانال‌های بلک‌لیست:**\n"]
        for r in rows:
            lines.append(f"• `{r['display_name']}` (`{r['channel_key']}`)")
        await update.message.reply_text("\n".join(lines))
        return

    if action in ("remove", "del", "delete"):
        if len(args) < 2:
            await update.message.reply_text("❌ نام کانال را بنویسید.")
            return
        ok = await remove_channel_blacklist(" ".join(args[1:]))
        await update.message.reply_text(
            "✅ از بلک‌لیست حذف شد." if ok else "❌ در بلک‌لیست نبود."
        )
        return

    channel = " ".join(args)
    if await add_channel_blacklist(channel):
        await update.message.reply_text(f"✅ کانال `{channel}` به بلک‌لیست اضافه شد.")
    else:
        await update.message.reply_text("❌ نام کانال نامعتبر است.")


async def cmd_blockword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "📋 **کلمات ممنوع جستجو**\n\n"
            "`/blockword کلمه` — افزودن\n"
            "`/blockword remove کلمه` — حذف\n"
            "`/blockword list` — لیست"
        )
        return

    action = args[0].lower()
    if action == "list":
        rows = await list_blocked_words()
        if not rows:
            await update.message.reply_text("📭 لیست خالی است.")
            return
        words = [f"• `{r['word']}`" for r in rows[:80]]
        extra = f"\n\n... و {len(rows) - 80} مورد دیگر" if len(rows) > 80 else ""
        await update.message.reply_text(
            "🚫 **کلمات ممنوع:**\n" + "\n".join(words) + extra
        )
        return

    if action in ("remove", "del", "delete"):
        if len(args) < 2:
            await update.message.reply_text("❌ کلمه را بنویسید.")
            return
        ok = await remove_blocked_word(" ".join(args[1:]))
        await update.message.reply_text(
            "✅ حذف شد." if ok else "❌ در لیست نبود."
        )
        return

    word = " ".join(args)
    if await add_blocked_word(word):
        await update.message.reply_text(f"✅ کلمه به لیست ممنوع اضافه شد.")
    else:
        await update.message.reply_text("❌ کلمه نامعتبر است (حداقل ۲ حرف).")


async def cmd_monitor_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    from services.hourly_monitoring import send_hourly_monitoring_report

    await update.message.reply_text("⏳ در حال تهیه و ارسال گزارش...")
    try:
        await send_hourly_monitoring_report(context, also_send_to=chat_id)
        await update.message.reply_text("✅ گزارش (فایل) به کانال مانیتورینگ ارسال شد.")
    except Exception:
        logger.exception("Failed to build/send monitoring report")
        await update.message.reply_text("❌ خطا در تهیه گزارش مانیتورینگ.")
