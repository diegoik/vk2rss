import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager


# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure the SQLite database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///vk2rss.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# VK API configuration
app.config["VK_API_TOKEN"] = os.environ.get("VK_API_TOKEN", "")
app.config["VK_API_VERSION"] = "5.131"  # Use a stable VK API version

# RSS configuration
app.config["SITE_URL"] = os.environ.get("SITE_URL", "http://localhost:5000")
app.config["FEED_CACHE_TIMEOUT"] = int(os.environ.get("FEED_CACHE_TIMEOUT", "300"))  # 5 minutes

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# initialize the app with the extension
db.init_app(app)

with app.app_context():
    # Import routes after app is created to avoid circular imports
    import routes  # noqa: F401
    
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    
    # Create database tables
    db.create_all()
    
    logger.info("Database tables created")

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))
