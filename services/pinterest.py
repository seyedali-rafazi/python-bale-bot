# services/pinterest.py

from ddgs import DDGS


from ddgs import DDGS
from urllib.parse import urlparse


ALLOWED_IMAGE_DOMAINS = [
    "pinimg.com",
    "i.pinimg.com",
]

BLOCKED_WORDS = [
    "porn",
    "porno",
    "xxx",
    "sex",
    "nude",
    "naked",
    "adult",
    "erotic",
    "nsfw",
    "18+",
]


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_pinimg_url(url: str) -> bool:
    domain = get_domain(url)
    return domain == "pinimg.com" or domain.endswith(".pinimg.com")


def has_blocked_word(text: str) -> bool:
    if not text:
        return False

    text = text.lower()
    return any(word in text for word in BLOCKED_WORDS)


def search_pinterest_images(query, max_results=10):
    try:
        query = query.strip()

        pinterest_query = (
            f"{query} site:pinterest.com "
            "-porn -porno -xxx -sex -nude -naked -adult -erotic -nsfw"
        )

        images = []
        seen = set()

        with DDGS() as ddgs:
            results = ddgs.images(
                pinterest_query,
                max_results=max_results * 3,
                safesearch="strict",
            )

            for res in results:
                image_url = res.get("image")
                page_url = res.get("url") or ""
                title = res.get("title") or ""

                if not image_url:
                    continue

                combined = f"{image_url} {page_url} {title}"

                if has_blocked_word(combined):
                    continue

                # مهم‌ترین فیلتر
                # فقط عکس‌هایی که واقعاً از CDN پینترست هستند
                if not is_pinimg_url(image_url):
                    continue

                if image_url in seen:
                    continue

                seen.add(image_url)
                images.append(image_url)

                if len(images) >= max_results:
                    break

        return images

    except Exception as e:
        print(f"Pinterest Search Error: {e}")
        return []
