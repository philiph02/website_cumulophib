from .base import *
import os

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-pythonanywhere-settings")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# UPDATED: We added your new domain here so the site works
ALLOWED_HOSTS = [
    '.pythonanywhere.com',
    'localhost', 
    '127.0.0.1',
    'www.cumulophib.com',
    'cumulophib.com'
]

# Security Setting: Allow forms to work on your new domain
CSRF_TRUSTED_ORIGINS = ['https://www.cumulophib.com', 'https://cumulophib.com']

# Datenbank: Wir nutzen wieder SQLite, genau wie auf deinem PC
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

# Statische Dateien (CSS/Bilder)
STATIC_ROOT = os.path.join(BASE_DIR, "static")
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# --- EMAIL SETTINGS (iCloud+) ---
# This tells Django to use Apple's servers to send mail
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.mail.me.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Login Details
EMAIL_HOST_USER = 'pheinrich210'   # Your Apple ID Login
EMAIL_HOST_PASSWORD = 'diwa-negn-bnpn-gjft'  # Your App-Specific Password
DEFAULT_FROM_EMAIL = 'hello@cumulophib.com'  # Sender address

try:
    from .local import *
except ImportError:
    pass