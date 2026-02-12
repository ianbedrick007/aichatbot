from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# User model
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # ✅ 1:1 relationship: one user has one business (business is the "account")
    business = db.relationship('Business', backref='user', uselist=False, lazy=True,
                               cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if the provided password matches the hash"""
        return check_password_hash(self.password_hash, password)


# Message model
class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)

    # ✅ Messages belong to the business (not directly to the user)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)

    text = db.Column(db.Text, nullable=True)
    sender = db.Column(db.String(10), nullable=False)  # 'user' or 'bot'
    timestamp = db.Column(db.DateTime, default=datetime.now)

    # Relationship back to business
    business = db.relationship('Business', backref='messages', lazy=True)


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)

    # ✅ Products belong to the business
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    business = db.relationship('Business', backref='products', lazy=True)


class Business(db.Model):
    __tablename__ = 'businesses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)

    # ✅ 1:1: each business has exactly one user login
    # unique=True enforces "one user -> one business"
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)

    # ✅ NEW: WhatsApp phone number ID mapping
    # Changed to BigInteger to support large phone number IDs
    phone_number_id = db.Column(db.BigInteger, unique=True, nullable=True)

    # ✅ Business persona: defines the AI's personality/instructions
    persona = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
