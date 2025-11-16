# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "undetected-chromedriver>=3.5.0",
#     "python-dotenv>=0.19.0",
#     "pyyaml>=6.0.1",
#     "requests>=2.31.0",
#     "setuptools",
# ]
# ///

"""
Twitter Bookmarks Scraper - Clean Architecture
Modular design for extracting bookmarks with complete thread support
"""

import os
import sys
import json
import time
import random
import sqlite3
import ssl
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Fix SSL certificate verification for macOS/Python 3.13
ssl._create_default_https_context = ssl._create_unverified_context


class Logger:
    """Simple console logger"""
    
    @staticmethod
    def info(msg: str):
        print(f"[INFO] {msg}")
    
    @staticmethod
    def success(msg: str):
        print(f"✓ {msg}")
    
    @staticmethod
    def warning(msg: str):
        print(f"⚠️  {msg}")
    
    @staticmethod
    def error(msg: str):
        print(f"❌ {msg}")


class TwitterAuth:
    """Handles Twitter authentication"""
    
    def __init__(self, driver, username: str, password: str):
        self.driver = driver
        self.username = username
        self.password = password
    
    def login(self) -> bool:
        """Login to Twitter"""
        try:
            Logger.info("Logging into Twitter...")
            
            self.driver.get("https://twitter.com")
            time.sleep(random.uniform(2, 4))
            self.driver.get("https://twitter.com/i/flow/login")
            time.sleep(random.uniform(3, 5))
            
            # Username
            username_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
            )
            for char in self.username:
                username_input.send_keys(char)
                # More realistic typing speed with occasional pauses
                if random.random() < 0.1:  # 10% chance of a slightly longer pause
                    time.sleep(random.uniform(0.2, 0.4))
                else:
                    time.sleep(random.uniform(0.08, 0.18))
                # Occasionally simulate backspace/correction (5% chance)
                if random.random() < 0.05 and len(self.username) > 1:
                    time.sleep(random.uniform(0.1, 0.3))
                    username_input.send_keys(Keys.BACKSPACE)
                    time.sleep(random.uniform(0.05, 0.15))
                    username_input.send_keys(char)
            time.sleep(random.uniform(0.8, 2.0))
            username_input.send_keys(Keys.RETURN)
            time.sleep(random.uniform(2.5, 5.0))

            # Password
            password_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
            )
            for char in self.password:
                password_input.send_keys(char)
                # Similar realistic typing patterns for password
                if random.random() < 0.1:  # 10% chance of a slightly longer pause
                    time.sleep(random.uniform(0.15, 0.35))
                else:
                    time.sleep(random.uniform(0.06, 0.16))
                # Password typing is usually more deliberate, fewer corrections
            time.sleep(random.uniform(0.6, 1.8))
            password_input.send_keys(Keys.RETURN)
            time.sleep(random.uniform(3.5, 7.0))
            
            # Verify login
            try:
                WebDriverWait(self.driver, 15).until(
                    lambda d: "home" in d.current_url.lower() or 
                             len(d.find_elements(By.CSS_SELECTOR, '[data-testid="AppTabBar_Home_Link"]')) > 0
                )
                Logger.success("Login successful!")
                return True
            except:
                Logger.warning("Login status unclear")
                return True
        except Exception as e:
            Logger.error(f"Login failed: {str(e)}")
            return False


class TweetParser:
    """Parses tweet elements into structured data"""
    
    @staticmethod
    def parse(tweet_element) -> Optional[Dict[str, Any]]:
        """Extract data from a tweet element"""
        try:
            data = {}
            
            # User info
            try:
                user_elem = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]')
                lines = user_elem.text.split('\n')
                data['display_name'] = lines[0] if lines else 'N/A'
                data['username'] = lines[1] if len(lines) > 1 else 'N/A'
                
                profile_link = user_elem.find_element(By.CSS_SELECTOR, 'a[href^="/"]')
                data['user_id'] = profile_link.get_attribute('href').split('/')[-1]
            except:
                data['user_id'] = data.get('username', 'N/A')
            
            # Tweet URL and ID
            try:
                link = tweet_element.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                data['url'] = link.get_attribute('href')
                data['tweet_id'] = data['url'].split('/status/')[-1].split('?')[0].split('/')[0]
            except:
                return None
            
            # Reply detection
            data['is_reply'] = False
            try:
                tweet_element.find_element(By.XPATH, ".//*[contains(text(), 'Replying to')]")
                data['is_reply'] = True
            except:
                pass
            
            # Text
            try:
                text_elem = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                data['text'] = text_elem.text
            except:
                data['text'] = ''
            
            # Timestamp
            try:
                time_elem = tweet_element.find_element(By.CSS_SELECTOR, 'time')
                data['timestamp'] = time_elem.get_attribute('datetime')
                data['readable_time'] = time_elem.text
            except:
                data['timestamp'] = None
            
            # Engagement
            try:
                reply_elem = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="reply"]')
                data['replies_count'] = int(reply_elem.get_attribute('aria-label').split()[0])
            except:
                data['replies_count'] = 0
            
            try:
                rt_elem = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="retweet"]')
                data['retweets_count'] = int(rt_elem.get_attribute('aria-label').split()[0])
            except:
                data['retweets_count'] = 0
            
            try:
                like_elem = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="like"]')
                data['likes_count'] = int(like_elem.get_attribute('aria-label').split()[0])
            except:
                data['likes_count'] = 0
            
            # Media
            has_photo = len(tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="tweetPhoto"]')) > 0
            has_video = len(tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="videoPlayer"]')) > 0
            data['has_media'] = has_photo or has_video
            data['media_type'] = 'photo' if has_photo else ('video' if has_video else 'none')
            
            return data
            
        except:
            return None


class ThreadExtractor:
    """Extracts complete conversation threads"""
    
    def __init__(self, driver, parser: TweetParser, *, max_scrolls: int = 40,
                 max_tweets: int = 30):
        self.driver = driver
        self.parser = parser
        self.max_scrolls = max_scrolls
        self.max_tweets = max_tweets
    
    def extract_complete_thread(self, tweet_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract complete thread by navigating to tweet and scrolling slowly
        Returns: List of all tweets in the thread (sorted by timestamp)
        """
        if not tweet_data.get('is_reply') or not tweet_data.get('tweet_id'):
            return []
        
        try:
            current_url = self.driver.current_url
            original_window = self.driver.current_window_handle
            thread_window = None
            tweet_id = tweet_data['tweet_id']
            
            Logger.info(f"Extracting thread for tweet {tweet_id}...")
            
            # Navigate to tweet in a temporary tab when possible to avoid losing scroll position
            tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
            try:
                self.driver.switch_to.new_window('tab')
                thread_window = self.driver.current_window_handle
            except Exception:
                try:
                    existing_handles = set(self.driver.window_handles)
                    self.driver.execute_script("window.open('about:blank','_blank');")
                    WebDriverWait(self.driver, 5).until(
                        lambda d: len(d.window_handles) > len(existing_handles)
                    )
                    new_handles = [h for h in self.driver.window_handles if h not in existing_handles]
                    if new_handles:
                        thread_window = new_handles[0]
                        self.driver.switch_to.window(thread_window)
                except Exception:
                    thread_window = None
                    self.driver.switch_to.window(original_window)
            
            self.driver.get(tweet_url)
            time.sleep(5)
            
            # Scroll to very top
            print("      ⬆️  Scrolling to top...")
            for _ in range(20):
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.3)
            time.sleep(3)
            
            # Slow scroll and extract
            print("      📜 Extracting tweets...")
            seen_ids = set()
            all_tweets = []
            scroll_count = 0
            no_new_count = 0
            target_found = False
            
            while scroll_count < self.max_scrolls and no_new_count < 8:
                elements = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
                
                new_count = 0
                for elem in elements:
                    try:
                        # Force render
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.2)
                        
                        parsed = self.parser.parse(elem)
                        if not parsed or not parsed.get('tweet_id'):
                            continue
                        if parsed['tweet_id'] in seen_ids:
                            continue
                        seen_ids.add(parsed['tweet_id'])
                        all_tweets.append(parsed)
                        new_count += 1
                        
                        text = parsed.get('text', '')
                        num = re.match(r'^(\d+)\.', text)
                        preview = f"#{num.group(1)}" if num else text[:30]
                        print(f"         ✓ {preview}")
                        if parsed['tweet_id'] == tweet_id:
                            target_found = True
                            break
                    except:
                        continue
                
                if new_count > 0:
                    no_new_count = 0
                else:
                    no_new_count += 1
                
                if len(all_tweets) >= self.max_tweets:
                    Logger.info("Reached max tweets for thread; stopping to avoid infinite scroll")
                    break
                if target_found:
                    Logger.info("Encountered bookmarked tweet; stopping thread crawl")
                    break
                
                # Tiny scroll
                self.driver.execute_script("window.scrollBy(0, 150);")
                time.sleep(1.5)
                
                # Trigger every 5 scrolls
                if scroll_count % 5 == 0:
                    self.driver.execute_script("window.scrollBy(0, -100);")
                    time.sleep(0.5)
                    self.driver.execute_script("window.scrollBy(0, 100);")
                    time.sleep(1)
                
                scroll_count += 1
            
            # Sort by timestamp
            all_tweets.sort(key=lambda t: t.get('timestamp') or '')
            
            if all_tweets:
                Logger.success(f"Extracted {len(all_tweets)} tweets from thread")
                # Update parent_tweet_id to root
                root_id = all_tweets[0]['tweet_id']
                tweet_data['parent_tweet_id'] = root_id
            
            # Return to bookmarks
            if thread_window:
                self.driver.close()
                self.driver.switch_to.window(original_window)
            else:
                self.driver.get(current_url)
                time.sleep(2)
            
            return all_tweets
            
        except Exception as e:
            Logger.error(f"Thread extraction failed: {str(e)}")
            try:
                if thread_window and thread_window in self.driver.window_handles:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                else:
                    self.driver.get(current_url)
                    time.sleep(2)
            except Exception:
                pass
            return []


class DatabaseManager:
    """Manages SQLite database operations"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = None
        self.init_database()
    
    def init_database(self):
        """Initialize database schema"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                display_name TEXT
            )
        ''')
        
        # Tweets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY,
                user_id TEXT,
                text TEXT,
                timestamp TEXT,
                url TEXT,
                replies_count INTEGER,
                retweets_count INTEGER,
                likes_count INTEGER,
                has_media BOOLEAN,
                media_type TEXT,
                is_reply BOOLEAN,
                parent_tweet_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (parent_tweet_id) REFERENCES tweets(tweet_id)
            )
        ''')
        
        # Bookmarks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                tweet_id TEXT PRIMARY KEY,
                bookmarked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_parent ON tweets(parent_tweet_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON tweets(timestamp)')
        
        self.conn.commit()
        Logger.success(f"Database initialized: {self.db_path}")
    
    def save_user(self, tweet_data: Dict[str, Any]):
        """Save user to database"""
        if not tweet_data.get('user_id'):
            return
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, display_name)
            VALUES (?, ?, ?)
        ''', (tweet_data['user_id'], tweet_data.get('username'), tweet_data.get('display_name')))
        self.conn.commit()
    
    def save_tweet(self, tweet_data: Dict[str, Any], is_bookmarked: bool = False):
        """Save tweet to database"""
        if not tweet_data.get('tweet_id'):
            return
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tweets (
                tweet_id, user_id, text, timestamp, url,
                replies_count, retweets_count, likes_count,
                has_media, media_type, is_reply, parent_tweet_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tweet_data['tweet_id'],
            tweet_data.get('user_id'),
            tweet_data.get('text'),
            tweet_data.get('timestamp'),
            tweet_data.get('url'),
            tweet_data.get('replies_count', 0),
            tweet_data.get('retweets_count', 0),
            tweet_data.get('likes_count', 0),
            tweet_data.get('has_media', False),
            tweet_data.get('media_type', 'none'),
            tweet_data.get('is_reply', False),
            tweet_data.get('parent_tweet_id')
        ))
        
        if is_bookmarked:
            cursor.execute('INSERT OR IGNORE INTO bookmarks (tweet_id) VALUES (?)', 
                          (tweet_data['tweet_id'],))
        
        self.conn.commit()
    
    def get_thread_from_db(self, tweet_id: str) -> List[Dict[str, Any]]:
        """Get complete thread from database using recursive query"""
        cursor = self.conn.cursor()
        
        # Find root
        root_id = tweet_id
        for _ in range(20):
            cursor.execute('SELECT parent_tweet_id FROM tweets WHERE tweet_id = ?', (root_id,))
            result = cursor.fetchone()
            if result and result['parent_tweet_id']:
                root_id = result['parent_tweet_id']
            else:
                break
        
        # Get all tweets in thread
        cursor.execute('''
            WITH RECURSIVE thread AS (
                SELECT * FROM tweets WHERE tweet_id = ?
                UNION ALL
                SELECT t.* FROM tweets t 
                JOIN thread th ON t.parent_tweet_id = th.tweet_id
            )
            SELECT * FROM thread ORDER BY timestamp ASC
        ''', (root_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def close(self):
        if self.conn:
            self.conn.close()


class Exporter:
    """Exports data to various formats"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def to_json(self, data: List[Dict], filename: str) -> Path:
        """Export to JSON"""
        path = self.output_dir / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path
    
    def to_individual_files(self, db: DatabaseManager, timestamp: str) -> Path:
        """Create individual JSON file for each bookmark with complete thread"""
        output_dir = self.output_dir / f'individual_bookmarks_{timestamp}'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cursor = db.conn.cursor()
        cursor.execute('SELECT tweet_id, user_id FROM bookmarks JOIN tweets USING(tweet_id)')
        bookmarks = cursor.fetchall()
        
        Logger.info(f"Creating {len(bookmarks)} individual files...")
        
        for bookmark in bookmarks:
            tweet_id = bookmark['tweet_id']
            user_id = bookmark['user_id']
            
            # Get bookmarked tweet
            cursor.execute('SELECT * FROM tweets WHERE tweet_id = ?', (tweet_id,))
            tweet = dict(cursor.fetchone())
            
            # Get complete thread
            thread = db.get_thread_from_db(tweet_id)
            
            structure = {
                "bookmarked_tweet": tweet,
                "is_part_of_thread": len(thread) > 1,
                "thread": thread,
                "conversation_root": thread[0]['tweet_id'] if thread else tweet_id,
                "metadata": {
                    "total_tweets_in_thread": len(thread),
                    "bookmarked_at": datetime.now().isoformat()
                }
            }
            
            filename = f"{tweet_id}_{user_id}.json"
            with open(output_dir / filename, 'w', encoding='utf-8') as f:
                json.dump(structure, f, indent=2, ensure_ascii=False)
            
            print(f"   ✓ {filename} ({len(thread)} tweets)")
        
        Logger.success(f"Individual files saved to: {output_dir.name}/")
        return output_dir


class TwitterBookmarksScraper:
    """Main scraper class orchestrating all components"""
    
    def __init__(self, username: str, password: str, output_dir: Path):
        self.username = username
        self.password = password
        self.output_dir = Path(output_dir)
        self.driver = None
        self.db = None
        self.parser = TweetParser()
        self.exporter = Exporter(self.output_dir)
        self.bookmarks = []
        self.seen_ids = set()
    
    def setup_driver(self):
        """Setup Chrome driver"""
        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')

        # Try to detect Chrome version or use a compatible version
        try:
            self.driver = uc.Chrome(options=options, version_main=129)  # Match your Chrome version
        except Exception as e:
            Logger.warning(f"Failed with version 129: {e}")
            try:
                # Fallback to automatic version detection
                self.driver = uc.Chrome(options=options, version_main=None)
            except Exception as e2:
                Logger.warning(f"Failed with auto detection: {e2}")
                # Last resort - try without version specification
                self.driver = uc.Chrome(options=options)

        return self.driver

    def _prime_bookmarks_feed(self):
        """Force-load the full bookmarks feed once before incremental passes"""
        try:
            Logger.info("Priming bookmarks timeline with full-depth scroll...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
        except Exception as e:
            Logger.warning(f"Bookmark priming scroll failed: {e}")

    def _scroll_one_viewport(self, wait_seconds: float = 2.0) -> bool:
        """Scroll down by exactly one viewport height to keep tweets in DOM"""
        try:
            previous_offset = self.driver.execute_script(
                "return window.pageYOffset || document.documentElement.scrollTop || 0;"
            )
            viewport_height = self.driver.execute_script("return window.innerHeight || 900;")
            self.driver.execute_script("window.scrollBy(0, arguments[0]);", viewport_height)
            time.sleep(wait_seconds)
            current_offset = self.driver.execute_script(
                "return window.pageYOffset || document.documentElement.scrollTop || 0;"
            )

            # If we didn't actually move, we've likely hit the end of the feed
            if abs(current_offset - previous_offset) < 5:
                Logger.info("No further movement detected while scrolling; stopping early.")
                return False
            return True
        except Exception as e:
            Logger.warning(f"Incremental scroll failed: {e}")
            time.sleep(wait_seconds)
            return False

    def scrape_bookmarks(self, max_scrolls: int = 100) -> List[Dict[str, Any]]:
        """Scrape all bookmarks"""
        Logger.info("Starting bookmark extraction...")

        self.driver.get("https://twitter.com/i/bookmarks")
        time.sleep(5)
        self._prime_bookmarks_feed()
        
        scroll_count = 0
        no_new_count = 0
        
        while scroll_count < max_scrolls and no_new_count < 3:
            scroll_count += 1
            print(f"\n📜 Scroll {scroll_count}/{max_scrolls}")
            
            elements = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
            new_count = 0
            
            for elem in elements:
                try:
                    parsed = self.parser.parse(elem)
                    if not parsed or parsed['tweet_id'] in self.seen_ids:
                        continue
                    
                    self.seen_ids.add(parsed['tweet_id'])
                    self.bookmarks.append(parsed)
                    new_count += 1
                    
                    # Save to database
                    self.db.save_user(parsed)
                    
                    # Extract thread if reply
                    if parsed.get('is_reply'):
                        extractor = ThreadExtractor(self.driver, self.parser)
                        thread_tweets = extractor.extract_complete_thread(parsed)
                        
                        if thread_tweets:
                            # Link all to root
                            root_id = thread_tweets[0]['tweet_id']
                            print(f"      🔗 Linking {len(thread_tweets)} tweets to root")
                            
                            for i, tt in enumerate(thread_tweets):
                                self.db.save_user(tt)
                                # Set parent_tweet_id for non-root tweets
                                if i > 0 and not tt.get('parent_tweet_id'):
                                    tt['parent_tweet_id'] = root_id
                                self.db.save_tweet(tt, is_bookmarked=False)
                    
                    # Save bookmarked tweet
                    self.db.save_tweet(parsed, is_bookmarked=True)
                    
                    preview = parsed.get('text', '')[:50]
                    print(f"   ✓ [{len(self.bookmarks)}] {preview}...")
                    
                except Exception as e:
                    continue
            
            print(f"   📊 New: {new_count} | Total: {len(self.bookmarks)}")
            
            if new_count == 0:
                no_new_count += 1
            else:
                no_new_count = 0
            
            # Scroll exactly one viewport height to keep DOM-loaded tweets visible
            if not self._scroll_one_viewport():
                no_new_count += 1
                if no_new_count >= 3:
                    Logger.info("Halting because no new tweets are loading with incremental scrolls.")
                break
        
        Logger.success(f"Extracted {len(self.bookmarks)} bookmarks")
        return self.bookmarks
    
    def export_results(self):
        """Export all results"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Flat JSON
        json_path = self.exporter.to_json(self.bookmarks, f'bookmarks_{timestamp}.json')
        Logger.success(f"JSON: {json_path.name}")
        
        # Individual files with threads
        individual_dir = self.exporter.to_individual_files(self.db, timestamp)
        
        return json_path, individual_dir
    
    def run(self):
        """Main execution flow"""
        try:
            # Setup
            db_path = self.output_dir / 'twitter_bookmarks.db'
            self.db = DatabaseManager(db_path)
            self.setup_driver()
            
            # Auth
            auth = TwitterAuth(self.driver, self.username, self.password)
            if not auth.login():
                return
            
            # Scrape
            self.scrape_bookmarks(max_scrolls=1000)
            
            # Export
            if self.bookmarks:
                self.export_results()
                
                # Stats
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM tweets")
                total_tweets = cursor.fetchone()[0]
                
                print("\n" + "="*60)
                print("🎉 SUCCESS!")
                print("="*60)
                print(f"📑 Bookmarks: {len(self.bookmarks)}")
                print(f"📊 Total tweets in DB: {total_tweets}")
                print(f"📁 Output: {self.output_dir}")
                print("="*60)
            
            input("\nPress Enter to close...")
            
        except KeyboardInterrupt:
            Logger.warning("Interrupted by user")
        except Exception as e:
            Logger.error(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                self.driver.quit()
            if self.db:
                self.db.close()


def main():
    # Load environment
    script_dir = Path(__file__).parent
    load_dotenv(script_dir / '.env')
    
    username = os.getenv('TWITTER_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')
    
    if not username or not password:
        Logger.error("Set TWITTER_USERNAME and TWITTER_PASSWORD in .env")
        sys.exit(1)
    
    # Run scraper
    output_dir = script_dir / 'output_data'
    scraper = TwitterBookmarksScraper(username, password, output_dir)
    scraper.run()


if __name__ == "__main__":
    main()
