import os
import logging
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort, Response, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from app import app, db
from models import User, VKFeed
from vk_api import VKAPIClient, VKAPIError, get_source_info
from feed_generator import RSSFeedGenerator, generate_access_token

logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """Home page route."""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
            
        login_user(user, remember=True)
        next_page = request.args.get('next')
        
        return redirect(next_page or url_for('dashboard'))
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate form data
        if not all([username, email, password, confirm_password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
            
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username is already taken', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email is already registered', 'danger')
            return redirect(url_for('register'))
            
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """User logout route."""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard showing their feeds."""
    feeds = VKFeed.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', feeds=feeds)

@app.route('/feeds/add', methods=['GET', 'POST'])
@login_required
def add_feed():
    """Add a new VK feed."""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description', '')
        vk_source_type = request.form.get('vk_source_type')
        vk_source_id = request.form.get('vk_source_id', '').strip()
        items_count = int(request.form.get('items_count', 20))
        include_attachments = 'include_attachments' in request.form
        include_comments = 'include_comments' in request.form
        is_public = 'is_public' in request.form
        
        # Basic validation
        if not all([title, vk_source_type, vk_source_id]):
            flash('Title and VK source information are required', 'danger')
            return redirect(url_for('add_feed'))
            
        try:
            # Validate the VK source by fetching info
            source_info = get_source_info(vk_source_type, vk_source_id)
            
            # If title is not provided, use the one from VK
            if not title:
                title = source_info.get('title')
                
            # Create the feed
            feed = VKFeed(
                user_id=current_user.id,
                title=title,
                description=description,
                vk_source_type=vk_source_type,
                vk_source_id=vk_source_id,
                items_count=items_count,
                include_attachments=include_attachments,
                include_comments=include_comments,
                is_public=is_public,
                access_token=generate_access_token()
            )
            
            db.session.add(feed)
            db.session.commit()
            
            flash('Feed added successfully!', 'success')
            return redirect(url_for('dashboard'))
            
        except VKAPIError as e:
            flash(f'Error validating VK source: {e}', 'danger')
            return redirect(url_for('add_feed'))
            
    return render_template('add_feed.html')

@app.route('/feeds/<int:feed_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_feed(feed_id):
    """Edit an existing VK feed."""
    feed = VKFeed.query.get_or_404(feed_id)
    
    # Check ownership
    if feed.user_id != current_user.id:
        abort(403)
        
    if request.method == 'POST':
        feed.title = request.form.get('title')
        feed.description = request.form.get('description', '')
        feed.vk_source_type = request.form.get('vk_source_type')
        feed.vk_source_id = request.form.get('vk_source_id', '').strip()
        feed.items_count = int(request.form.get('items_count', 20))
        feed.include_attachments = 'include_attachments' in request.form
        feed.include_comments = 'include_comments' in request.form
        feed.is_public = 'is_public' in request.form
        
        # Basic validation
        if not all([feed.title, feed.vk_source_type, feed.vk_source_id]):
            flash('Title and VK source information are required', 'danger')
            return redirect(url_for('edit_feed', feed_id=feed_id))
            
        try:
            # Validate the VK source by fetching info
            get_source_info(feed.vk_source_type, feed.vk_source_id)
            
            # Update the feed
            feed.updated_at = datetime.utcnow()
            db.session.commit()
            
            flash('Feed updated successfully!', 'success')
            return redirect(url_for('dashboard'))
            
        except VKAPIError as e:
            flash(f'Error validating VK source: {e}', 'danger')
            return redirect(url_for('edit_feed', feed_id=feed_id))
            
    return render_template('edit_feed.html', feed=feed)

@app.route('/feeds/<int:feed_id>/delete', methods=['POST'])
@login_required
def delete_feed(feed_id):
    """Delete a feed."""
    feed = VKFeed.query.get_or_404(feed_id)
    
    # Check ownership
    if feed.user_id != current_user.id:
        abort(403)
        
    db.session.delete(feed)
    db.session.commit()
    
    flash('Feed deleted successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/feeds/<int:feed_id>/preview')
@login_required
def preview_feed(feed_id):
    """Preview a feed before subscribing."""
    feed = VKFeed.query.get_or_404(feed_id)
    
    # Check ownership or if feed is public
    if feed.user_id != current_user.id and not feed.is_public:
        abort(403)
        
    # Generate the feed content
    generator = RSSFeedGenerator(feed)
    feed_content = generator.generate_feed()
    
    # Get source information for display
    try:
        source_info = get_source_info(feed.vk_source_type, feed.vk_source_id)
    except VKAPIError:
        source_info = {
            'title': feed.title,
            'link': '#',
            'description': feed.description,
            'image': None
        }
    
    return render_template('preview_feed.html', feed=feed, source_info=source_info)

@app.route('/feeds/<int:feed_id>.rss')
def get_feed(feed_id):
    """Get the RSS feed content."""
    feed = VKFeed.query.get_or_404(feed_id)
    token = request.args.get('token')
    
    # Check if feed is public or token is valid
    if not feed.is_public and feed.access_token != token:
        abort(403)
        
    # Generate the feed content
    generator = RSSFeedGenerator(feed)
    feed_content = generator.generate_feed()
    
    # Return as XML
    return Response(feed_content, mimetype='application/rss+xml')

@app.route('/api/check-vk-source', methods=['POST'])
@login_required
def check_vk_source():
    """API endpoint to check if a VK source is valid."""
    source_type = request.json.get('source_type')
    source_id = request.json.get('source_id', '').strip()
    
    if not source_type or not source_id:
        return jsonify({'valid': False, 'message': 'Source type and ID are required'})
        
    try:
        source_info = get_source_info(source_type, source_id)
        return jsonify({
            'valid': True,
            'info': source_info
        })
    except VKAPIError as e:
        return jsonify({
            'valid': False,
            'message': str(e)
        })

@app.context_processor
def utility_processor():
    """Utility functions for templates."""
    def format_datetime(dt):
        if dt:
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        return 'Never'
        
    def get_feed_url(feed):
        """Get the full URL for a feed."""
        return url_for('get_feed', feed_id=feed.id, token=feed.access_token, _external=True)
    
    # Add current date for use in templates
    now = datetime.now()
    
    return {
        'format_datetime': format_datetime,
        'get_feed_url': get_feed_url,
        'now': now
    }

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template('500.html'), 500

@app.route('/import-feeds', methods=['GET', 'POST'])
@login_required
def import_feeds():
    """Import multiple feeds from a list of URLs."""
    if request.method == 'POST':
        urls_text = request.form.get('urls', '')
        default_title = request.form.get('default_title', 'VK Feed')
        vk_source_type = request.form.get('vk_source_type', 'group')
        include_attachments = 'include_attachments' in request.form
        include_comments = 'include_comments' in request.form
        is_public = 'is_public' in request.form
        items_count = int(request.form.get('items_count', 20))
        
        # Parse the URLs from the text input
        url_lines = [line.strip() for line in urls_text.split('\n') if line.strip()]
        
        created_feeds = 0
        errors = []
        
        for line in url_lines:
            # Skip comments if line starts with #
            if line.startswith('#'):
                continue
                
            # Split the line into URL and optional comment/title
            parts = line.split('#', 1)
            url = parts[0].strip()
            
            # Skip empty lines
            if not url:
                continue
                
            # Use comment as title if available, otherwise use default title
            title = parts[1].strip() if len(parts) > 1 else default_title
            
            try:
                # Extract ID from URL
                from vk_api import extract_vk_id_from_url, get_source_info
                source_id = extract_vk_id_from_url(url)
                
                # Get source info using the selected source type
                source_info = get_source_info(vk_source_type, source_id)
                
                # Create a better title if none was provided
                if not title or title == default_title:
                    title = source_info.get('title', default_title)
                
                # Create a new feed
                feed = VKFeed(
                    user_id=current_user.id,
                    title=title,
                    description=source_info.get('description', ''),
                    vk_source_type=vk_source_type,
                    vk_source_id=source_id,
                    items_count=items_count,
                    include_attachments=include_attachments,
                    include_comments=include_comments,
                    is_public=is_public,
                    access_token=generate_access_token()
                )
                
                db.session.add(feed)
                created_feeds += 1
            except Exception as e:
                logger.error(f"Error importing feed {url}: {str(e)}")
                errors.append(f"Error al procesar {url}: {str(e)}")
        
        if created_feeds > 0:
            db.session.commit()
            flash(f'Se han creado {created_feeds} feeds correctamente.', 'success')
        else:
            flash('No se ha podido crear ningún feed. Por favor, verifica las URLs e inténtalo de nuevo.', 'warning')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            
        return redirect(url_for('dashboard'))
        
    return render_template('import_feeds.html')
