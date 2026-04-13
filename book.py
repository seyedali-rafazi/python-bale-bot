# book.py

import requests
import os

def search_books(query):
    """جستجوی کتاب در منابع آزاد و برگرداندن لیست نتایج"""
    results = []
    
    # ۱. جستجو در dBooks (معمولاً کتاب‌های علمی، استارتاپ و تکنولوژی)
    try:
        d_url = f"https://www.dbooks.org/api/search/{query}"
        d_resp = requests.get(d_url, timeout=10).json()
        if d_resp.get('status') == 'ok':
            for item in d_resp.get('books', [])[:3]: # گرفتن ۳ نتیجه اول
                results.append({
                    'id': item.get('id'),
                    'title': item.get('title'),
                    'author': item.get('authors'),
                    'source': 'dBooks.org',
                    'has_pdf': True, # dBooks همیشه PDF دارد
                    'pdf_url': 'needs_fetch' # لینک دانلود باید جداگانه دریافت شود
                })
    except Exception as e:
        print(f"DBooks error: {e}")

    # ۲. جستجو در Project Gutenberg (از طریق Gutendex)
    try:
        g_url = f"https://gutendex.com/books?search={query}"
        g_resp = requests.get(g_url, timeout=10).json()
        for item in g_resp.get('results', [])[:3]: # گرفتن ۳ نتیجه اول
            # بررسی اینکه آیا فایل PDF در فرمت‌ها وجود دارد یا خیر
            formats = item.get('formats', {})
            pdf_url = formats.get('application/pdf')
            has_pdf = bool(pdf_url)
            
            authors = ", ".join([a.get('name', 'Unknown') for a in item.get('authors', [])])
            
            results.append({
                'id': str(item['id']),
                'title': item.get('title'),
                'author': authors,
                'source': 'Project Gutenberg',
                'has_pdf': has_pdf,
                'pdf_url': pdf_url
            })
    except Exception as e:
        print(f"Gutenberg error: {e}")

    return results

def get_dbooks_download_url(book_id):
    """دریافت لینک مستقیم PDF برای کتاب‌های dBooks"""
    try:
        url = f"https://www.dbooks.org/api/book/{book_id}"
        resp = requests.get(url, timeout=10).json()
        return resp.get('download')
    except:
        return None

def download_pdf(url, title):
    """دانلود فایل PDF و ذخیره آن در سرور"""
    try:
        # ساخت یک نام امن برای فایل
        safe_title = "".join([c for c in title if c.isalnum() or c in [' ', '-', '_']]).strip()
        file_path = f"{safe_title}.pdf"
        
        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return file_path
    except Exception as e:
        print(f"PDF Download error: {e}")
        return None
