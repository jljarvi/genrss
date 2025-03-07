import os
import sys
import re
from datetime import datetime, timezone
import json
import requests
import feedgenerator
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from xml.dom import minidom


# Load the previously stored feed data (for incremental updates)
def load_existing_entries(feed_path):
    if os.path.exists(feed_path):
        with open(feed_path, 'r') as f:
            return json.load(f)
    return {}


# Save the current feed data (to avoid adding duplicate entries)
def save_entries(feed_path, entries):
    with open(feed_path, 'w') as f:
        json.dump(entries, f)


def parse_date(date_str):
    # Convert date strings like "February 25, 2024" to datetime
    try:
        return datetime.strptime(date_str, "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def extract_blog_posts(url):
    response = requests.get(url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = []
    seen_links = set()
    
    # Try different article selectors in order of preference
    blog_elements = (
        soup.find_all(class_='blog-basic-grid--container') or  # Squarespace style
        soup.find_all(['article']) or  # Semantic HTML
        soup.find_all('a', class_=lambda x: x and 'group' in str(x).lower()) or  # Ollama style
        soup.find_all(['div', 'section'], class_=lambda x: x and any(c in str(x).lower() 
            for c in ['blog-post', 'post', 'article', 'entry']))  # Generic blog classes
    )
    
    for element in blog_elements:
        # Skip navigation elements
        if element.find_parent(['nav', 'header', 'footer']):
            continue
            
        # Get the main link first - we'll use this to check for duplicates
        main_link = None
        link_elem = element if element.name == 'a' else element.find('a', href=True)
        if link_elem and 'href' in link_elem.attrs:
            href = link_elem['href']
            # Skip category, tag, and read more links
            if any(x in href.lower() for x in ['/category/', '/tag/', '/page/']):
                continue
            if any(x in link_elem.get_text().lower() for x in ['category', 'read more']):
                continue
                
            main_link = href if href.startswith('http') else url.rstrip('/') + '/' + href.lstrip('/')
            
            # Skip if we've seen this link before
            if main_link in seen_links:
                continue
            seen_links.add(main_link)
        else:
            continue
            
        # Now get title, description, and author
        title = None
        description = None
        author = None
        
        # Look for title in common heading elements and classes
        title_elem = (
            element.find(class_='blog-title') or  # Squarespace style
            element.find(['h1', 'h2'], class_=lambda x: x and 'title' in str(x).lower()) or
            element.find(['h1', 'h2']) or  # Any heading
            element.find(class_='font-semibold')  # Ollama style
        )
        if title_elem:
            title_anchor = title_elem.find('a')
            title = (title_anchor.get_text() if title_anchor else title_elem.get_text()).strip()
            
        # Look for description in common excerpt/content classes
        desc_elem = (
            element.find(class_='blog-excerpt') or  # Squarespace style
            element.find(['p'], class_=lambda x: x and any(c in str(x).lower() 
                for c in ['excerpt', 'summary', 'description'])) or
            element.find('p', class_='mt-4') or  # Ollama style
            element.find('p')  # First paragraph
        )
        if desc_elem:
            paragraphs = desc_elem.find_all('p')
            if paragraphs:
                description = ' '.join(p.get_text().strip() for p in paragraphs)
            else:
                description = desc_elem.get_text().strip()
        
        # Look for author in meta sections or author-specific elements
        author_elem = (
            element.find(class_='blog-author') or  # Squarespace style
            element.find(['span', 'div'], class_=lambda x: x and 'author' in str(x).lower()) or
            element.find(['a', 'span', 'div'], attrs={'rel': 'author'})
        )
        if author_elem:
            author = author_elem.get_text().strip()
            
        if title and main_link and len(title) > 3:  # Ensure title is meaningful
            articles.append({
                'title': title,
                'description': description or title,
                'link': main_link,
                'pub_date': datetime.now(timezone.utc),
                'author': author
            })
    
    return articles


def generate_rss(feed_title, feed_link, feed_description, articles):
    # Clean up article content by removing excessive whitespace
    for article in articles:
        article['title'] = ' '.join(article['title'].split())
        article['description'] = ' '.join(article['description'].split())
    
    feed = feedgenerator.Rss201rev2Feed(
        title=feed_title,
        link=feed_link,
        description=feed_description,
        language="en"
    )
    
    for article in articles:
        item_kwargs = {
            'title': article['title'],
            'link': article['link'],
            'description': article['description'],
            'pubdate': article['pub_date']
        }
        
        # Only add author if it exists
        if article.get('author'):
            item_kwargs['author'] = article['author']
        
        feed.add_item(**item_kwargs)
    
    # Convert feed to string and format XML
    xml_str = feed.writeString('utf-8')
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://ollama.com/blog"
    
    try:
        # Create data and feeds directories if they don't exist
        os.makedirs('../data', exist_ok=True)
        os.makedirs('../feeds', exist_ok=True)
        
        # Create filenames from the URL
        domain = urlparse(url).netloc.replace('www.', '')
        feed_file = os.path.join('../feeds', f"{domain.split('.')[0]}.xml")
        data_file = os.path.join('../data', f"{domain.split('.')[0]}.json")
        
        # Load existing entries
        existing_entries = load_existing_entries(data_file)
        
        # If this is a new feed, generate the title
        if not existing_entries:
            # Get the site name from either the title tag or domain
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to get site name from title tag
            title_tag = soup.find('title')
            site_name = None
            if title_tag:
                # Clean up common title patterns
                site_title = title_tag.string.strip()
                
                # Remove common suffixes and prefixes
                site_title = re.split(r'[-|·•]|\s+[—–-]\s+|\b(?:Blog|Home|Website)\b', site_title)[0].strip()
                
                # If title starts with "Blog", try to find a better name
                if site_title.lower().startswith('blog'):
                    # Try meta tags first
                    meta_title = soup.find('meta', property=['og:site_name', 'twitter:title'])
                    if meta_title and meta_title.get('content'):
                        site_title = meta_title['content'].strip()
                    else:
                        # Remove "Blog" from start if it's there
                        site_title = re.sub(r'^Blog\s*[-|·•]?\s*', '', site_title)
                
                site_name = site_title
            
            # If no title found or title is too generic, use domain name
            if not site_name or site_name.lower() in ['blog', 'home', 'website']:
                site_name = domain.split('.')[0].title()
            
            # Clean up any remaining whitespace or punctuation
            site_name = site_name.strip('- |·•').strip()
            
            # Store the feed title
            existing_entries['feed_title'] = f"{site_name} Blog Feed"
            existing_entries['feed_description'] = f"RSS feed generated from {url}"
            existing_entries['entries'] = {}
        
        # Get new articles
        articles = extract_blog_posts(url)
        if articles:
            # Only add new articles that we haven't seen before
            new_articles = []
            for article in articles:
                if article['link'] not in existing_entries['entries']:
                    new_articles.append(article)
                    existing_entries['entries'][article['link']] = {
                        'title': article['title'],
                        'description': article['description'],
                        'pub_date': article['pub_date'].isoformat(),
                        'author': article.get('author')
                    }
            
            # Convert stored entries back to articles format
            all_articles = []
            for link, data in existing_entries['entries'].items():
                all_articles.append({
                    'title': data['title'],
                    'description': data['description'],
                    'link': link,
                    'pub_date': datetime.fromisoformat(data['pub_date']),
                    'author': data.get('author')
                })
            
            # Generate the RSS feed with all articles
            rss_feed = generate_rss(
                existing_entries['feed_title'],
                url,
                existing_entries['feed_description'],
                all_articles
            )
            
            # Save the updated entries
            save_entries(data_file, existing_entries)
            
            # Save the RSS feed to file and print to stdout
            with open(feed_file, 'w', encoding='utf-8') as f:
                f.write(rss_feed)
            print(rss_feed)
        else:
            print("No blog posts found at the specified URL.")
    except Exception as e:
        print(f"Error processing the URL: {e}", file=sys.stderr)
