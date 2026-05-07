# services/research.py

import os
import re
import requests
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")
SCIHUB_BOT_USERNAME = os.getenv("SCIHUB_BOT_USERNAME")

download_lock = None


def clean_doi(doi: str) -> str:
    if not doi:
        return ""
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi).strip()
    return doi


def format_openalex_item(item) -> dict:
    title = item.get("title", "بدون عنوان")
    if not title:
        title = "بدون عنوان"

    authors_list = item.get("authorships", [])
    author_names = ", ".join(
        [a.get("author", {}).get("display_name", "") for a in authors_list[:3]]
    )
    if len(authors_list) > 3:
        author_names += " و همکاران"

    doi = item.get("doi", "ندارد")
    if doi and doi != "ندارد":
        doi = clean_doi(doi)

    year = item.get("publication_year", "نامشخص")
    citations = item.get("cited_by_count", 0)

    # پیدا کردن تمام لینک‌های PDF مستقیم از locations
    pdf_urls = []
    for loc in item.get("locations", []):
        pdf_url = loc.get("pdf_url")
        if pdf_url and pdf_url not in pdf_urls:
            pdf_urls.append(pdf_url)

    is_oa = item.get("open_access", {}).get("is_oa", False)

    return {
        "title": title,
        "authors": author_names if author_names else "نامشخص",
        "doi": doi,
        "year": str(year),
        "citations": citations,
        "is_oa": is_oa,
        "pdf_urls": pdf_urls,  # لیست لینک‌های مستقیم احتمالی
    }


def search_article_by_name(query, page=1, min_year=None, sort_by="relevance"):
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": 5, "page": page}
    if sort_by == "citation":
        params["sort"] = "cited_by_count:desc"
    if min_year:
        params["filter"] = f"from_publication_date:{min_year}-01-01"
    headers = {"User-Agent": "BaleBot/1.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = [
            format_openalex_item(item)
            for item in data.get("results", [])
            if format_openalex_item(item)
        ]
        return results
    except Exception as e:
        print(f"Error searching OpenAlex: {e}")
        return []


def search_article_by_doi(doi_input: str) -> list:
    doi_clean = clean_doi(doi_input)
    url = f"https://api.openalex.org/works/https://doi.org/{doi_clean}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return [format_openalex_item(response.json())]
    except Exception as e:
        print(f"Error fetching DOI from OpenAlex: {e}")
    return []


# --- توابع جدید برای منابع جایگزین ---


def get_unpaywall_pdf(doi: str) -> str:
    """دریافت لینک PDF از API رایگان Unpaywall"""
    email = "your_email@example.com"  # بهتر است ایمیل واقعی خود را اینجا قرار دهید
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("best_oa_location"):
                return data["best_oa_location"].get("url_for_pdf")
    except:
        pass
    return None


def get_semanticscholar_pdf(doi: str) -> str:
    """دریافت لینک PDF از API رایگان Semantic Scholar"""
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf"
    )
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("openAccessPdf"):
                return data["openAccessPdf"].get("url")
    except:
        pass
    return None


# ------------------------------------


async def download_direct_pdf(url: str, doi_or_name: str) -> str:
    """دانلود مستقیم فایل با بررسی نوع محتوا و حجم"""
    if not url:
        return None
    try:
        os.makedirs("downloads", exist_ok=True)
        safe_name = doi_or_name.replace("/", "_").replace("\\", "_")
        file_path = f"downloads/{safe_name}_direct.pdf"

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=15, stream=True)
        content_type = response.headers.get("Content-Type", "").lower()

        if response.status_code == 200 and "application/pdf" in content_type:
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(1024):
                    if chunk:
                        f.write(chunk)

            if (
                os.path.exists(file_path) and os.path.getsize(file_path) > 10240
            ):  # حجم بیشتر از 10 کیلوبایت
                return file_path
            else:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None
    except Exception as e:
        print(f"Error downloading direct PDF from {url}: {e}")
    return None


async def download_pdf_via_telegram(doi_input: str) -> str:
    """دریافت از طریق ربات تلگرامی Sci-Hub"""
    global download_lock
    if download_lock is None:
        download_lock = asyncio.Lock()

    doi = clean_doi(doi_input)
    if not doi:
        return None

    async with download_lock:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            print("⚠️ خطا: اکانت تلگرام لاگین نیست.")
            await client.disconnect()
            return None

        downloaded_file_path = None
        try:
            await client.delete_dialog(SCIHUB_BOT_USERNAME)
            await client.send_message(SCIHUB_BOT_USERNAME, doi)
            await asyncio.sleep(12)  # افزایش زمان به 12 ثانیه برای اطمینان

            messages = await client.get_messages(SCIHUB_BOT_USERNAME, limit=3)
            for msg in messages:
                if msg.file and msg.file.ext == ".pdf":
                    os.makedirs("downloads", exist_ok=True)
                    safe_name = doi.replace("/", "_").replace("\\", "_")
                    file_path = f"downloads/{safe_name}.pdf"

                    await client.download_media(message=msg, file=file_path)
                    downloaded_file_path = file_path
                    break
        except Exception as e:
            print(f"Error in Telegram fetch: {e}")
        finally:
            await client.disconnect()

        return downloaded_file_path


async def smart_download_pdf(article: dict, status_message) -> str:
    """
    مدیریت هوشمند و چندلایه‌ی دانلود مقاله همراه با اطلاع‌رسانی به کاربر.
    status_message: شیء پیامی است که با await status_message.edit_text آپدیت می‌شود.
    """
    doi = article.get("doi")
    is_oa = article.get("is_oa")

    if is_oa:
        await status_message.edit_text(
            "ℹ️ این مقاله رایگان (Open Access) است، اما ممکن است ناشر لینک مستقیم PDF نداده باشد. سیستم در حال بررسی منابع مختلف است..."
        )
        await asyncio.sleep(2)

    # 1. تلاش اول: لینک‌های OpenAlex
    await status_message.edit_text("🔍 تلاش اول: جستجو در مخازن OpenAlex...")
    for pdf_url in article.get("pdf_urls", []):
        file_path = await download_direct_pdf(pdf_url, doi)
        if file_path:
            return file_path

    if not doi or doi == "ندارد":
        return None

    # 2. تلاش دوم: Unpaywall
    await status_message.edit_text("🔍 تلاش دوم: جستجو در پایگاه Unpaywall...")
    unpaywall_url = get_unpaywall_pdf(doi)
    if unpaywall_url:
        file_path = await download_direct_pdf(unpaywall_url, doi)
        if file_path:
            return file_path

    # 3. تلاش سوم: Semantic Scholar
    await status_message.edit_text("🔍 تلاش سوم: جستجو در پایگاه Semantic Scholar...")
    semantic_url = get_semanticscholar_pdf(doi)
    if semantic_url:
        file_path = await download_direct_pdf(semantic_url, doi)
        if file_path:
            return file_path

    # 4. تلاش چهارم: Sci-Hub
    await status_message.edit_text(
        "🤖 تلاش چهارم: درخواست از دیتابیس Sci-Hub (ممکن است کمی طول بکشد)..."
    )
    file_path = await download_pdf_via_telegram(doi)
    if file_path:
        return file_path

    # 5. پایان تلاش‌ها
    await status_message.edit_text(
        "❌ متاسفانه فایل PDF مستقیم این مقاله در هیچ‌یک از ۴ منبع (OpenAlex, Unpaywall, Semantic Scholar, Sci-Hub) یافت نشد."
    )
    return None


def get_article_data_for_citation(doi_input: str) -> dict:
    """دریافت اطلاعات مقاله از OpenAlex برای تولید رفرنس"""
    doi_clean = clean_doi(doi_input)
    url = f"https://api.openalex.org/works/https://doi.org/{doi_clean}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()

            title = data.get("title", "Unknown Title")
            year = str(data.get("publication_year", "Unknown Year"))
            doi_val = clean_doi(data.get("doi", ""))

            # استخراج نام ژورنال
            journal = "Unknown Journal"
            primary_location = data.get("primary_location")
            if primary_location and primary_location.get("source"):
                journal = primary_location["source"].get(
                    "display_name", "Unknown Journal"
                )

            # استخراج لیست نویسندگان
            authors_list = []
            for authorship in data.get("authorships", []):
                author_name = authorship.get("author", {}).get("display_name")
                if author_name:
                    authors_list.append(author_name)

            return {
                "title": title,
                "year": year,
                "doi": doi_val,
                "journal": journal,
                "authors_list": authors_list,
            }
    except Exception as e:
        print(f"Error fetching data for citation: {e}")

    return None
