# config.py
from decouple import config

DATABASE_URL = config("DATABASE_URL")
SENDER_EMAIL = config("SENDER_EMAIL")
SENDER_PASSWORD = config("SENDER_PASSWORD")
JWT_SECRET_KEY = config("JWT_SECRET_KEY")