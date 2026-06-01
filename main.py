import asyncio
import json
import logging
from bs4 import BeautifulSoup
import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_URL = "https://search.jabber.network/channels/{page}"
CONCURRENCY_LIMIT = 5


def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    rooms = []
    
    room_cards = soup.find_all("li", class_="roomcard")
    for card in room_cards:
        room_data = {}
        
        # Title
        title_el = card.find(class_="title")
        room_data["title"] = title_el.get_text(strip=True) if title_el else ""
        
        # JID
        copy_el = card.find("a", class_="copy-to-clipboard")
        if copy_el and copy_el.get("data-cliptext"):
            room_data["jid"] = copy_el["data-cliptext"]
        else:
            # Fallback just because
            addr_el = card.find(class_="address")
            room_data["jid"] = addr_el.get_text(strip=True) if addr_el else ""
            
        # Online users count
        users_el = card.find("span", class_="n")
        room_data["users_online"] = users_el.get("data-content", "0") if users_el else "0"
        
        # Description
        descr_el = card.find(class_="descr")
        room_data["description"] = descr_el.get_text(strip=True) if descr_el else ""
        
        # Primary Language
        lang_wrap = card.find("li", title="Primary room language")
        if lang_wrap:
            # Drop the hidden text element before getting text
            hidden_span = lang_wrap.find("span", class_="visually-hidden")
            if hidden_span:
                hidden_span.decompose()
            room_data["language"] = lang_wrap.get_text(strip=True)
        else:
            room_data["language"] = "Unknown"
            
        # Tags
        tags_wrap = card.find("ul", class_="tags")
        if tags_wrap:
            room_data["tags"] = [t.get_text(strip=True).lstrip("#") for t in tags_wrap.find_all("li")]
        else:
            room_data["tags"] = []
            
        rooms.append(room_data)
        
    return rooms


def find_last_page(html):
    # Finds the total page count from pagination elements
    soup = BeautifulSoup(html, "lxml")
    pagination = soup.find("nav", class_="pagination")
    if not pagination:
        return 1
    
    links = pagination.find_all("a")
    pages = []
    for a in links:
        text = a.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
            
    return max(pages) if pages else 1


async def fetch_page(session, page_num, semaphore):
    # Fetches a single page
    url = BASE_URL.format(page=page_num)
    async with semaphore:
        try:
            logging.info(f"Fetching page {page_num}...")
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    logging.error(f"Error {response.status} on page {page_num}")
                    return None
                return await response.text()
        except Exception as e:
            logging.error(f"Failed to fetch page {page_num}: {e}")
            return None


async def main():
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    # Custom headers to identify the client
    headers = {
        "User-Agent": "mucoso/1.0 (+https://github.com/nixietab/mucoso)"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        first_page_html = await fetch_page(session, 1, semaphore)
        if not first_page_html:
            logging.critical("Could not read the home page index structure. Exiting.")
            return
            
        last_page = find_last_page(first_page_html)
        logging.info(f"Detected total target array sizing: {last_page} pages.")
        
        tasks = []
        for p in range(1, last_page + 1):
            tasks.append(fetch_page(session, p, semaphore))
            
        pages_html = await asyncio.gather(*tasks)
        
        all_mucs = []
        for html in pages_html:
            if html:
                rooms_extracted = parse_page(html)
                all_mucs.extend(rooms_extracted)
                
        output_file = "jabber_mucs.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_mucs, f, ensure_ascii=False, indent=2)
            
        logging.info(f"Crawling finished successfully. Total objects saved: {len(all_mucs)} > {output_file}")


if __name__ == "__main__":
    asyncio.run(main())