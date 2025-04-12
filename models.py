import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    # Define the relationship to VKFeed
    feeds = db.relationship('VKFeed', backref='user', lazy=True, cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class VKFeed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)  # Cambiado a Text para permitir descripciones largas
    
    # VK source information
    vk_source_type = db.Column(db.String(20), nullable=False)  # 'user', 'group', 'page'
    vk_source_id = db.Column(db.String(255), nullable=False)  # Aumentado a 255 para URLs largas
    
    # RSS feed configuration
    items_count = db.Column(db.Integer, default=20)
    include_attachments = db.Column(db.Boolean, default=True)
    include_comments = db.Column(db.Boolean, default=False)
    translate_titles = db.Column(db.Boolean, default=True)  # Traducir automáticamente los títulos
    
    # Feed access control
    is_public = db.Column(db.Boolean, default=False)
    access_token = db.Column(db.String(64), unique=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    last_fetched = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<VKFeed {self.title} ({self.vk_source_type}:{self.vk_source_id})>'


class FeedCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('vk_feed.id'), nullable=False)
    cached_content = db.Column(db.Text)
    cached_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    # Define the relationship to VKFeed
    feed = db.relationship('VKFeed')
    
    def __repr__(self):
        return f'<FeedCache for feed_id={self.feed_id}>'
