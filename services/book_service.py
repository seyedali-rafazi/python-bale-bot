import io
import requests


def search_books_by_name(query: str, limit: int = 5):
    """
    جستجوی کتاب از طریق API سایت‌های dbooks.org و Gutenberg (Gutendex)
    """
    books = []

    # 1. جستجو در dbooks.org (بیشتر کتاب‌های برنامه‌نویسی و کامپیوتر - فرمت PDF)
    try:
        url = f"https://www.dbooks.org/api/search/{query}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                for item in data.get("books", []):
                    books.append(
                        {
                            "source": "dbooks",
                            "id": item.get("id"),
                            "title": item.get("title")[:40],
                            "author": item.get("authors")[:30],
                            "year": "نامشخص",  # این API سال را برنمی‌گرداند
                            "ext": ".pdf",
                        }
                    )
                    if len(books) >= limit:
                        break
    except Exception as e:
        print(f"Error fetching from dbooks: {e}")

    # 2. در صورت نیاز، جستجو در گوتنبرگ برای تکمیل لیست (بیشتر فرمت‌های EPUB)
    if len(books) < limit:
        try:
            gut_url = f"https://gutendex.com/books/?search={query}"
            resp = requests.get(gut_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", []):
                    # پیدا کردن بهترین لینک دانلود (PDF یا EPUB)
                    formats = item.get("formats", {})
                    dl_link = None
                    ext = ""

                    if "application/pdf" in formats:
                        dl_link = formats["application/pdf"]
                        ext = ".pdf"
                    elif "application/epub+zip" in formats:
                        dl_link = formats["application/epub+zip"]
                        ext = ".epub"
                    elif "text/plain; charset=us-ascii" in formats:
                        dl_link = formats["text/plain; charset=us-ascii"]
                        ext = ".txt"

                    if dl_link:
                        author_name = "نامشخص"
                        if item.get("authors"):
                            author_name = item["authors"][0].get("name", "نامشخص")

                        books.append(
                            {
                                "source": "gutenberg",
                                "id": str(item.get("id")),
                                "title": item.get("title")[:40],
                                "author": author_name[:30],
                                "year": "نامشخص",
                                "link": dl_link,  # لینک دانلود مستقیم گوتنبرگ
                                "ext": ext,
                            }
                        )

                    if len(books) >= limit:
                        break
        except Exception as e:
            print(f"Error fetching from Gutenberg: {e}")

    return books


async def download_book_pdf(book_data: dict) -> io.BytesIO:
    """
    دانلود مستقیم فایل کتاب از سرور بر اساس منبع (dbooks یا گوتنبرگ)
    """
    try:
        source = book_data.get("source")
        download_url = None
        file_ext = book_data.get("ext", ".pdf")

        # اگر منبع dbooks باشد، باید از API دوم برای گرفتن لینک دانلود مستقیم استفاده کنیم
        if source == "dbooks":
            book_id = book_data.get("id")
            details_url = f"https://www.dbooks.org/api/book/{book_id}"
            resp = requests.get(details_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                download_url = data.get("download")

        # اگر منبع گوتنبرگ باشد، لینک دانلود را از قبل داریم
        elif source == "gutenberg":
            download_url = book_data.get("link")

        if not download_url:
            return None

        # دانلود فایل واقعی
        file_resp = requests.get(download_url, stream=True, timeout=60)
        if file_resp.status_code == 200:
            # بررسی محدودیت $50$ مگابایت تلگرام
            content_length = file_resp.headers.get("content-length")
            if content_length and int(content_length) > 50 * 1024 * 1024:
                print("حجم فایل بیشتر از 50 مگابایت است.")
                return None

            file_stream = io.BytesIO(file_resp.content)
            safe_title = "".join(
                x for x in book_data["title"] if x.isalnum() or x in " _-"
            )
            file_stream.name = (
                f"{safe_title[:30]}{file_ext}"  # پسوند فایل به درستی تنظیم می‌شود
            )

            return file_stream

    except Exception as e:
        print(f"Error downloading book: {e}")

    return None
