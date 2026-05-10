# services/pinterest.py

from ddgs import DDGS


def search_pinterest_images(query, max_results=10):
    try:
        with DDGS() as ddgs:
            # اضافه کردن کلمات کلیدی برای محدود کردن بهتر نتایج
            pinterest_query = f"{query} site:pinterest.com"

            # حتما safesearch="strict" را اضافه کنید
            results = list(
                ddgs.images(
                    pinterest_query,
                    max_results=max_results,
                    safesearch="strict",  # فیلتر کردن محتوای نامناسب
                )
            )
            return [res["image"] for res in results]
    except Exception as e:
        print(f"Pinterest Search Error: {e}")
        return []
