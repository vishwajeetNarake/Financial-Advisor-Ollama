import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId
import bcrypt
import os

class Database:
    def __init__(self):
        # Initialize MongoDB connection
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['loan_advisor']
    
    def store_application(self, application_data, user_id=None):
        """Store a new loan application in the database"""
        if user_id:
            application_data['user_id'] = ObjectId(user_id)
        
        result = self.db.applications.insert_one(application_data)
        return result.inserted_id
    
    def get_application(self, application_id):
        """Get a specific application by ID"""
        try:
            return self.db.applications.find_one({'_id': ObjectId(application_id)})
        except:
            return None
    
    def get_all_applications(self, user_id=None):
        """Get all applications, optionally filtered by user_id"""
        query = {}
        if user_id:
            query['user_id'] = ObjectId(user_id)
        
        return list(self.db.applications.find(query).sort('created_at', -1))
    
    def register_user(self, username, password, email):
        """Register a new user"""
        # Check if username already exists
        if self.db.users.find_one({'username': username}):
            return None
        
        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create the user
        user = {
            'username': username,
            'password': hashed_password,
            'email': email
        }
        
        result = self.db.users.insert_one(user)
        return result.inserted_id
    
    def login_user(self, username, password):
        """Verify user credentials and return user if valid"""
        user = self.db.users.find_one({'username': username})
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            return user
        
        return None

    # New methods for chat functionality
    def store_chat(self, chat_data):
        """Store a chat message and its response"""
        result = self.db.chats.insert_one(chat_data)
        return result.inserted_id

    def get_chat_history(self, application_id):
        """Get the chat history for a specific application"""
        chats = list(self.db.chats.find(
            {"application_id": application_id},
            {"_id": 0}  # Exclude _id field for easier JSON serialization
        ).sort("timestamp", 1))  # Sort by timestamp ascending
        return chats