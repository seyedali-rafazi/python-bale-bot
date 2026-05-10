from ddgs import DDGS


def search_pinterest_images(query, max_results=10):
    try:
        with DDGS() as ddgs:
            # اضافه کردن site:pinterest.com به کوئری تا فقط در پینترست بگردد
            pinterest_query = f"{query} site:pinterest.com"
            results = list(
                ddgs.images(
                    pinterest_query, max_results=max_results, safesearch="strict"
                )
            )
            return [res["image"] for res in results]
    except Exception as e:
        print(f"Pinterest Search Error: {e}")
        return []
