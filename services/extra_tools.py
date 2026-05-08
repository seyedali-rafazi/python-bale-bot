# services/extra_tools.py

import aiohttp
from services.research import clean_doi

translate_lock = None


async def get_bibtex_from_openalex(doi_input: str) -> str:
    """دریافت اطلاعات مقاله از OpenAlex و تبدیل آن به فرمت BibTeX"""
    doi_clean = clean_doi(doi_input)
    url = f"https://api.openalex.org/works/https://doi.org/{doi_clean}"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    title = data.get("title", "Unknown Title")
                    year = str(data.get("publication_year", "Unknown Year"))
                    doi_val = clean_doi(data.get("doi", "Unknown_DOI"))

                    # استخراج نویسندگان
                    authors_list = []
                    for authorship in data.get("authorships", []):
                        author_name = authorship.get("author", {}).get("display_name")
                        if author_name:
                            authors_list.append(author_name)
                    authors_str = " and ".join(authors_list)

                    # استخراج ژورنال
                    journal = "Unknown Journal"
                    primary_location = data.get("primary_location")
                    if primary_location and primary_location.get("source"):
                        journal = primary_location["source"].get(
                            "display_name", "Unknown Journal"
                        )

                    # ساخت کلید یکتا برای BibTeX
                    bib_key = f"{doi_val.split('/')[-1]}_{year}".replace(
                        ".", "_"
                    ).replace("-", "_")

                    # قالب‌بندی به شکل BibTeX
                    bibtex = (
                        f"@article{{{bib_key},\n"
                        f"  title={{{title}}},\n"
                        f"  author={{{authors_str}}},\n"
                        f"  journal={{{journal}}},\n"
                        f"  year={{{year}}},\n"
                        f"  doi={{{doi_val}}}\n"
                        f"}}"
                    )
                    return bibtex
    except Exception as e:
        print(f"Error fetching BibTeX: {e}")

    return None
