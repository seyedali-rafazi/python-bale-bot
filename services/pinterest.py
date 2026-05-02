from duckduckgo_search import DDGS


def search_pinterest_images(query, max_results=10):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=max_results))
            return [res["image"] for res in results]
    except Exception as e:
        print(f"Pinterest Search Error: {e}")
        return []
