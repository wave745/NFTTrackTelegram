import sqlite3
import logging
import json
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

def init_db():
    """Initialize the database with necessary tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        settings TEXT DEFAULT '{}'
    )
    ''')
    
    # Create tracked_collections table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracked_collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        blockchain TEXT NOT NULL,
        marketplace TEXT NOT NULL,
        collection_address TEXT NOT NULL,
        collection_name TEXT,
        last_timestamp TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id),
        UNIQUE (user_id, blockchain, collection_address)
    )
    ''')
    
    # Create transaction_history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transaction_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        blockchain TEXT NOT NULL,
        marketplace TEXT NOT NULL,
        collection_address TEXT NOT NULL,
        token_id TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        price REAL,
        currency TEXT,
        buyer TEXT,
        seller TEXT,
        timestamp TEXT,
        transaction_hash TEXT,
        UNIQUE (blockchain, transaction_hash, token_id)
    )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def add_user(user_id, first_name, username):
    """Add a new user to the database or update existing user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR REPLACE INTO users (user_id, first_name, username)
    VALUES (?, ?, ?)
    ''', (user_id, first_name, username))
    
    conn.commit()
    conn.close()
    logger.info(f"User {user_id} added/updated in database")

def get_user_settings(user_id):
    """Get user settings from the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT settings FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return json.loads(result['settings'])
    return {
        "alert_type": "all",  # Options: "all", "sales", "purchases"
        "update_frequency": "instant"  # Options: "instant", "10min", "hourly"
    }

def update_user_settings(user_id, settings):
    """Update user settings in the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE users SET settings = ? WHERE user_id = ?
    ''', (json.dumps(settings), user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"Settings updated for user {user_id}")

def add_collection(user_id, blockchain, marketplace, collection_address, collection_name=None):
    """Add a collection to track for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO tracked_collections 
        (user_id, blockchain, marketplace, collection_address, collection_name)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, blockchain, marketplace, collection_address, collection_name))
        
        conn.commit()
        conn.close()
        logger.info(f"Collection {collection_address} added for user {user_id}")
        return True
    except sqlite3.IntegrityError:
        conn.close()
        logger.info(f"Collection {collection_address} already being tracked by user {user_id}")
        return False

def remove_collection(user_id, blockchain, collection_address):
    """Remove a tracked collection for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    DELETE FROM tracked_collections 
    WHERE user_id = ? AND blockchain = ? AND collection_address = ?
    ''', (user_id, blockchain, collection_address))
    
    deleted = cursor.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        logger.info(f"Collection {collection_address} removed for user {user_id}")
    else:
        logger.info(f"Collection {collection_address} not found for user {user_id}")
    
    return deleted

def get_user_collections(user_id):
    """Get all collections tracked by a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT blockchain, marketplace, collection_address, collection_name
    FROM tracked_collections
    WHERE user_id = ?
    ''', (user_id,))
    
    collections = cursor.fetchall()
    conn.close()
    
    return [dict(collection) for collection in collections]

def get_all_tracked_collections():
    """Get all tracked collections across all users"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT DISTINCT blockchain, marketplace, collection_address, collection_name 
    FROM tracked_collections
    ''')
    
    collections = cursor.fetchall()
    conn.close()
    
    return [dict(collection) for collection in collections]

def get_collection_trackers(blockchain, collection_address):
    """Get all users tracking a specific collection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT tc.user_id, u.settings
    FROM tracked_collections tc
    JOIN users u ON tc.user_id = u.user_id
    WHERE tc.blockchain = ? AND tc.collection_address = ?
    ''', (blockchain, collection_address))
    
    trackers = cursor.fetchall()
    conn.close()
    
    return [{"user_id": tracker["user_id"], "settings": json.loads(tracker["settings"])} 
            for tracker in trackers]

def update_last_timestamp(blockchain, collection_address, timestamp):
    """Update the last checked timestamp for a collection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE tracked_collections 
    SET last_timestamp = ?
    WHERE blockchain = ? AND collection_address = ?
    ''', (timestamp, blockchain, collection_address))
    
    conn.commit()
    conn.close()

def get_last_timestamp(blockchain, collection_address):
    """Get the last checked timestamp for a collection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT last_timestamp 
    FROM tracked_collections
    WHERE blockchain = ? AND collection_address = ?
    LIMIT 1
    ''', (blockchain, collection_address))
    
    result = cursor.fetchone()
    conn.close()
    
    return result['last_timestamp'] if result and result['last_timestamp'] else None

def add_transaction(blockchain, marketplace, collection_address, token_id, transaction_type, 
                   price, currency, buyer, seller, timestamp, transaction_hash):
    """Add a new transaction to the history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO transaction_history 
        (blockchain, marketplace, collection_address, token_id, transaction_type, 
         price, currency, buyer, seller, timestamp, transaction_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (blockchain, marketplace, collection_address, token_id, transaction_type, 
             price, currency, buyer, seller, timestamp, transaction_hash))
        
        conn.commit()
        transaction_id = cursor.lastrowid
        conn.close()
        logger.info(f"Transaction {transaction_hash} added to history")
        return transaction_id
    except sqlite3.IntegrityError:
        conn.close()
        logger.info(f"Transaction {transaction_hash} already in history")
        return None
