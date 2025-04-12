import logging
import time
from datetime import datetime, timedelta
from feedgen.feed import FeedGenerator
from flask import url_for, current_app
import uuid
import pytz

from vk_api import VKAPIClient, get_source_info, format_post_content, VKAPIError
from models import VKFeed, FeedCache
from app import db
from translator import translate_text

logger = logging.getLogger(__name__)

class RSSFeedGenerator:
    """Generate RSS feeds from VK content."""
    
    def __init__(self, feed_config):
        """
        Initialize the feed generator.
        
        Args:
            feed_config: VKFeed model instance with feed configuration
        """
        self.feed_config = feed_config
        self.vk_client = VKAPIClient()
        
    def get_cached_feed(self):
        """
        Get the cached feed content if it exists and is not expired.
        
        Returns:
            Cached RSS content or None if no valid cache exists
        """
        cache_timeout = current_app.config.get('FEED_CACHE_TIMEOUT', 300)  # 5 minutes default
        
        # Check if we have a cached version
        cache = FeedCache.query.filter_by(feed_id=self.feed_config.id).first()
        
        if cache:
            cache_age = datetime.utcnow() - cache.cached_at
            if cache_age.total_seconds() < cache_timeout:
                logger.debug(f"Using cached feed for feed_id={self.feed_config.id}")
                return cache.cached_content
        
        return None
        
    def update_cache(self, content):
        """
        Update the feed cache with new content.
        
        Args:
            content: RSS feed content to cache
        """
        cache = FeedCache.query.filter_by(feed_id=self.feed_config.id).first()
        
        if cache:
            cache.cached_content = content
            cache.cached_at = datetime.utcnow()
        else:
            cache = FeedCache(
                feed_id=self.feed_config.id,
                cached_content=content,
                cached_at=datetime.utcnow()
            )
            db.session.add(cache)
        
        db.session.commit()
        
    def generate_feed(self):
        """
        Generate an RSS feed for the configured VK source.
        
        Returns:
            RSS feed content as a string
        """
        # Try to get from cache first
        cached = self.get_cached_feed()
        if cached:
            return cached
            
        logger.debug(f"Generating new feed for {self.feed_config.vk_source_type}:{self.feed_config.vk_source_id}")
        
        try:
            # Get source information
            source_info = get_source_info(
                self.feed_config.vk_source_type, 
                self.feed_config.vk_source_id
            )
            
            # Create feed generator
            fg = FeedGenerator()
            fg.id(url_for('get_feed', feed_id=self.feed_config.id, token=self.feed_config.access_token, _external=True))
            
            # Obtener título original y traducirlo
            original_title = self.feed_config.title or source_info['title']
            try:
                translated_title = translate_text(original_title, source_lang='ru', target_lang='es')
                if translated_title and translated_title != original_title:
                    logger.info(f"Título del feed traducido: '{original_title}' -> '{translated_title}'")
                    fg.title(translated_title)
                else:
                    fg.title(original_title)
            except Exception as e:
                logger.warning(f"Error al traducir título del feed: {e}")
                fg.title(original_title)
                
            fg.link(href=source_info['link'], rel='alternate')
            fg.description(self.feed_config.description or source_info['description'])
            fg.language('es')  # Cambiamos el idioma a español ya que estamos traduciendo
            
            # Set feed image if available
            if source_info.get('image'):
                fg.logo(source_info['image'])
            
            # Get wall posts
            owner_id = self.feed_config.vk_source_id
            try:
                response = self.vk_client.get_wall_posts(
                    owner_id=owner_id, 
                    count=self.feed_config.items_count
                )
                
                if response and 'items' in response:
                    posts = response['items']
                    
                    # Add each post as a feed entry
                    for post in posts:
                        self._add_post_to_feed(fg, post)
                    
                    # Update the last fetched timestamp
                    self.feed_config.last_fetched = datetime.utcnow()
                    db.session.commit()
                    
                    # Generate the feed content
                    feed_content = fg.rss_str(pretty=True).decode('utf-8')
                    
                    # Cache the content
                    self.update_cache(feed_content)
                    
                    return feed_content
                else:
                    logger.warning(f"No posts found for {owner_id}")
                    return f"<!-- No posts found for {owner_id} -->"
                
            except VKAPIError as e:
                logger.error(f"VK API error while generating feed: {e}")
                return f"<!-- Error generating feed: {e} -->"
                
        except Exception as e:
            logger.exception(f"Error generating feed: {e}")
            return f"<!-- Error generating feed: {e} -->"
    
    def _add_post_to_feed(self, feed_generator, post):
        """
        Add a VK post to the feed as an entry.
        
        Args:
            feed_generator: FeedGenerator instance
            post: VK post data
        """
        # Create a new feed entry
        entry = feed_generator.add_entry()
        
        # Generate a unique ID for the post
        post_id = post.get('id')
        owner_id = post.get('owner_id')
        entry.id(f"vk-post-{owner_id}_{post_id}")
        
        # Set the title - use the first line of text or a default
        text = post.get('text', '')
        title = text.split('\n')[0][:100] if text else f"Post {post_id}"
        if not title.strip():
            title = f"Post from {datetime.fromtimestamp(post.get('date', 0))}"
            
        # Traducir el título del ruso al español
        try:
            translated_title = translate_text(title, source_lang='ru', target_lang='es')
            # Si la traducción fue exitosa, utilizar el título traducido
            if translated_title and translated_title != title:
                logger.info(f"Título traducido: '{title}' -> '{translated_title}'")
                title = translated_title
        except Exception as e:
            logger.warning(f"Error al traducir título: {e}")
            
        entry.title(title)
        
        # Set the link to the original post
        post_url = f"https://vk.com/wall{owner_id}_{post_id}"
        entry.link(href=post_url)
        
        # Format the content
        content = format_post_content(post, self.feed_config.include_attachments)
        entry.content(content, type='html')
        
        # Set the publication date
        pub_date = datetime.fromtimestamp(post.get('date', 0))
        pub_date = pub_date.replace(tzinfo=pytz.UTC)
        entry.published(pub_date)
        
        # Add the author if available
        if 'signer_id' in post and post['signer_id']:
            entry.author(name=f"User ID: {post['signer_id']}")
        else:
            entry.author(name=f"Group ID: {abs(owner_id)}" if owner_id < 0 else f"User ID: {owner_id}")

def generate_access_token():
    """Generate a unique access token for feed access."""
    return str(uuid.uuid4()).replace('-', '')
