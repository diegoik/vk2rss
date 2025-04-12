import logging
import requests
import time
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)

class VKAPIError(Exception):
    """Exception raised for VK API errors."""
    pass

class VKAPIClient:
    """Client for interacting with the VK API."""
    
    def __init__(self, access_token=None, api_version=None):
        """
        Initialize the VK API client.
        
        Args:
            access_token: VK API access token, defaults to app config
            api_version: VK API version, defaults to app config
        """
        self.access_token = access_token or current_app.config.get('VK_API_TOKEN')
        self.api_version = api_version or current_app.config.get('VK_API_VERSION')
        self.base_url = "https://api.vk.com/method/"
        
    def _make_request(self, method, params=None):
        """
        Make a request to the VK API.
        
        Args:
            method: API method name
            params: Dictionary of parameters to pass to the API
            
        Returns:
            JSON response from the API
            
        Raises:
            VKAPIError: If the API returns an error
        """
        if params is None:
            params = {}
            
        # Add common parameters
        params['access_token'] = self.access_token
        params['v'] = self.api_version
        
        # Make the request
        url = f"{self.base_url}{method}"
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Check for API error
            if 'error' in data:
                error = data['error']
                error_msg = f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
                logger.error(error_msg)
                raise VKAPIError(error_msg)
                
            return data.get('response')
            
        except requests.RequestException as e:
            logger.error(f"Error making request to VK API: {e}")
            raise VKAPIError(f"Request to VK API failed: {e}")
        
    def get_wall_posts(self, owner_id, count=20, offset=0):
        """
        Get posts from a user or community wall.
        
        Args:
            owner_id: ID of the user or community (negative for communities) or domain
            count: Number of posts to retrieve
            offset: Offset for pagination
            
        Returns:
            List of wall posts
        """
        params = {
            'count': count,
            'offset': offset,
            'extended': 1  # Get extended information (profiles, groups)
        }
        
        # Process the owner_id parameter properly
        if '/' in owner_id or 'vk.com' in owner_id:
            owner_id = extract_vk_id_from_url(owner_id)
            logger.debug(f"Extracted ID for wall.get: {owner_id}")
        
        # Check if owner_id is numeric ID or domain name
        if owner_id.lstrip('-').isdigit():
            params['owner_id'] = owner_id
        else:
            params['domain'] = owner_id
        
        return self._make_request('wall.get', params)
    
    def get_group_info(self, group_id):
        """
        Get information about a group.
        
        Args:
            group_id: ID or screen name of the group
            
        Returns:
            Group information
        """
        # Process URL or complex ID
        if isinstance(group_id, str) and ('/' in group_id or 'vk.com' in group_id):
            group_id = extract_vk_id_from_url(group_id)
            logger.debug(f"Extracted group ID: {group_id}")
        
        params = {
            'group_id': group_id,
            'fields': 'description,name,screen_name'
        }
        
        return self._make_request('groups.getById', params)
    
    def get_user_info(self, user_id):
        """
        Get information about a user.
        
        Args:
            user_id: ID or screen name of the user
            
        Returns:
            User information
        """
        # Process URL or complex ID
        if isinstance(user_id, str) and ('/' in user_id or 'vk.com' in user_id):
            user_id = extract_vk_id_from_url(user_id)
            logger.debug(f"Extracted user ID: {user_id}")
        
        params = {
            'user_ids': user_id,
            'fields': 'photo_100,screen_name'
        }
        
        return self._make_request('users.get', params)
    
    def resolve_screen_name(self, screen_name):
        """
        Resolve a screen name to get object type and ID.
        
        Args:
            screen_name: Screen name to resolve
            
        Returns:
            Object type and ID
        """
        # Process URL or complex ID first
        if isinstance(screen_name, str) and ('/' in screen_name or 'vk.com' in screen_name):
            screen_name = extract_vk_id_from_url(screen_name)
            logger.debug(f"Extracted screen name: {screen_name}")
        
        # Skip attempting to resolve if it's already a numeric ID
        if isinstance(screen_name, str) and screen_name.lstrip('-').isdigit():
            # Determine the type based on the sign (negative = group, positive = user)
            object_id = int(screen_name)
            object_type = 'user' if object_id > 0 else 'group'
            return {'type': object_type, 'object_id': abs(object_id)}
        
        # Otherwise, call the API to resolve the screen name
        params = {
            'screen_name': screen_name
        }
        
        return self._make_request('utils.resolveScreenName', params)

def extract_vk_id_from_url(url):
    """
    Extract VK ID from a URL.
    
    Args:
        url: VK URL (e.g., https://vk.com/group_name or https://vk.com/wall-123456)
        
    Returns:
        Extracted ID or the original string if no ID is found
    """
    import re
    
    if not url:
        return url
    
    # Log the original URL for debugging
    logger.debug(f"Extracting ID from URL: {url}")
    
    # Extract numeric ID for a group with a negative ID
    group_id_pattern = r'group(-?\d+)'
    group_id_match = re.search(group_id_pattern, url)
    if group_id_match:
        return group_id_match.group(1)
    
    # Extract numeric ID for a user with ID
    user_id_pattern = r'id(\d+)'
    user_id_match = re.search(user_id_pattern, url)
    if user_id_match:
        return user_id_match.group(1)
    
    # Extract ID from wall URL pattern
    wall_pattern = r'wall(-?\d+)'
    wall_match = re.search(wall_pattern, url)
    if wall_match:
        return wall_match.group(1)
    
    # Extract numeric group ID after minus sign (common in URLs like vk.com/public-123456)
    minus_id_pattern = r'(?:public|club)-(\d+)'
    minus_id_match = re.search(minus_id_pattern, url)
    if minus_id_match:
        return f"-{minus_id_match.group(1)}"
    
    # Extract ID or screen name from VK URL
    url_pattern = r'vk\.com/(?!wall|id|club|public|group)([a-zA-Z0-9._]+)'
    url_match = re.search(url_pattern, url)
    if url_match:
        return url_match.group(1)
    
    # Extract just the last part of the URL for domains
    last_part_pattern = r'/([^/]+)/?$'
    last_part_match = re.search(last_part_pattern, url)
    if last_part_match:
        # Skip some common patterns we've already checked
        last_part = last_part_match.group(1)
        if last_part not in ['wall', 'id', 'club', 'public', 'group']:
            return last_part
    
    # If no patterns match, return the original string
    return url

def get_source_info(source_type, source_id):
    """
    Get information about a VK source (user, group, or page).
    
    Args:
        source_type: Type of the source ('user', 'group', 'page')
        source_id: ID of the source
        
    Returns:
        Dictionary with information about the source
    """
    client = VKAPIClient()
    
    # Process URLs or complex IDs
    if '/' in source_id or 'vk.com' in source_id:
        source_id = extract_vk_id_from_url(source_id)
        logger.debug(f"Extracted ID from URL: {source_id}")
    
    # Try to resolve screen name if it's not a numeric ID
    if not source_id.lstrip('-').isdigit():
        try:
            resolved = client.resolve_screen_name(source_id)
            if resolved:
                resolved_type = resolved.get('type')
                resolved_id = resolved.get('object_id')
                
                if resolved_type == 'user':
                    source_type = 'user'
                    source_id = resolved_id
                elif resolved_type in ('group', 'page'):
                    source_type = resolved_type
                    source_id = -resolved_id  # Group IDs are negative in wall.get
        except VKAPIError as e:
            logger.warning(f"Failed to resolve screen name {source_id}: {e}")
    
    # Get info based on the source type
    try:
        if source_type == 'user':
            info = client.get_user_info(source_id)
            if info and len(info) > 0:
                user = info[0]
                return {
                    'title': f"{user.get('first_name')} {user.get('last_name')}",
                    'link': f"https://vk.com/id{user.get('id')}",
                    'description': f"VK user profile for {user.get('first_name')} {user.get('last_name')}",
                    'image': user.get('photo_100')
                }
        else:  # group or page
            numeric_id = abs(int(source_id)) if str(source_id).lstrip('-').isdigit() else source_id
            info = client.get_group_info(numeric_id)
            if info and len(info) > 0:
                group = info[0]
                return {
                    'title': group.get('name'),
                    'link': f"https://vk.com/{group.get('screen_name')}",
                    'description': group.get('description', ''),
                    'image': group.get('photo_100')
                }
    except VKAPIError as e:
        logger.error(f"Failed to get source info for {source_type}:{source_id}: {e}")
    
    # Default fallback info
    return {
        'title': f"VK {source_type.capitalize()} {source_id}",
        'link': f"https://vk.com/{source_id}",
        'description': f"Content from VK {source_type} {source_id}",
        'image': None
    }

def format_post_content(post, include_attachments=True):
    """
    Format the content of a VK post for RSS.
    
    Args:
        post: VK post data
        include_attachments: Whether to include attachments
        
    Returns:
        HTML content for the post
    """
    content = []
    
    # Add text content
    if post.get('text'):
        content.append(f"<p>{post['text']}</p>")
    
    # Process attachments if requested
    if include_attachments and 'attachments' in post:
        for attachment in post['attachments']:
            attachment_type = attachment.get('type')
            
            if attachment_type == 'photo':
                photo = attachment.get('photo', {})
                # Find the largest size photo
                sizes = photo.get('sizes', [])
                if sizes:
                    # Sort by height and take the largest
                    sizes.sort(key=lambda s: s.get('height', 0), reverse=True)
                    largest = sizes[0]
                    img_url = largest.get('url')
                    content.append(f'<p><img src="{img_url}" style="max-width:100%;" /></p>')
            
            elif attachment_type == 'link':
                link = attachment.get('link', {})
                url = link.get('url')
                title = link.get('title', url)
                content.append(f'<p><a href="{url}" target="_blank">{title}</a></p>')
            
            elif attachment_type == 'video':
                video = attachment.get('video', {})
                video_id = video.get('id')
                owner_id = video.get('owner_id')
                title = video.get('title', 'Video')
                if video_id and owner_id:
                    video_url = f"https://vk.com/video{owner_id}_{video_id}"
                    content.append(f'<p><a href="{video_url}" target="_blank">{title}</a></p>')
            
            elif attachment_type == 'doc':
                doc = attachment.get('doc', {})
                url = doc.get('url')
                title = doc.get('title', 'Document')
                if url:
                    content.append(f'<p><a href="{url}" target="_blank">{title}</a></p>')
    
    # Add a link to the original post
    owner_id = post.get('owner_id')
    post_id = post.get('id')
    if owner_id and post_id:
        post_url = f"https://vk.com/wall{owner_id}_{post_id}"
        content.append(f'<p><a href="{post_url}" target="_blank">View original post on VK</a></p>')
    
    return "".join(content)
