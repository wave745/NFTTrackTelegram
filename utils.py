import logging
import time
import requests
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiting utility to prevent API abuse"""
    def __init__(self, max_calls, time_frame):
        self.max_calls = max_calls
        self.time_frame = time_frame  # in seconds
        self.calls = []
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            current_time = time.time()
            # Remove calls older than the time frame
            self.calls = [call_time for call_time in self.calls if current_time - call_time <= self.time_frame]
            
            if len(self.calls) >= self.max_calls:
                sleep_time = self.time_frame - (current_time - self.calls[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                    # Update current time after sleep
                    current_time = time.time()
            
            self.calls.append(current_time)
            return func(*args, **kwargs)
        
        return wrapper

def format_address(address, max_length=10):
    """Format blockchain address for display"""
    if not address:
        return "Unknown"
    
    if len(address) <= max_length:
        return address
        
    prefix = address[:max_length//2]
    suffix = address[-max_length//2:]
    return f"{prefix}...{suffix}"

def format_price(price, currency="ETH", decimals=4):
    """Format price for display"""
    if price is None:
        return "Unknown"
    
    try:
        price_float = float(price)
        return f"{price_float:.{decimals}f} {currency}"
    except (ValueError, TypeError):
        return f"{price} {currency}"

def get_current_timestamp():
    """Get current timestamp in ISO format with UTC timezone"""
    return datetime.now(pytz.UTC).isoformat()

def parse_timestamp(timestamp):
    """Parse ISO format timestamp to datetime object"""
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return None

@RateLimiter(max_calls=5, time_frame=1)  # 5 calls per second
def make_api_request(url, method="GET", headers=None, params=None, data=None, timeout=10):
    """Make an API request with rate limiting"""
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data,
            timeout=timeout
        )
        
        if response.status_code == 429:
            logger.warning("Rate limit exceeded. Backing off...")
            time.sleep(5)  # Simple backoff
            return make_api_request(url, method, headers, params, data, timeout)
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return None

def validate_ethereum_address(address):
    """Validate Ethereum address format"""
    if not address:
        return False
    
    # Basic validation - should be 0x followed by 40 hex characters
    if not address.startswith('0x') or len(address) != 42:
        return False
    
    try:
        # Check if it contains only hex characters after 0x
        int(address[2:], 16)
        return True
    except ValueError:
        return False
    
def validate_solana_address(address):
    """Validate Solana address format"""
    if not address:
        return False
    
    # Basic validation - should be a base58 string of approximately 32-44 characters
    if len(address) < 32 or len(address) > 44:
        return False
    
    # Check for base58 characters (0-9, A-Z except I, O, and l, and a-z except b)
    base58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    return all(c in base58_chars for c in address)

def format_transaction_alert(transaction, collection_info=None):
    """Format a transaction alert message for Telegram"""
    transaction_type = transaction.get('transaction_type', 'Unknown')
    emoji = "🔴" if transaction_type.lower() == "sale" else "🟢"
    
    collection_name = collection_info.get('collection_name') if collection_info else "Unknown Collection"
    if not collection_name and transaction.get('collection_name'):
        collection_name = transaction['collection_name']
    
    blockchain = transaction.get('blockchain', 'Unknown')
    token_id = transaction.get('token_id', 'Unknown')
    
    price = format_price(
        transaction.get('price'), 
        transaction.get('currency', get_blockchain_currency(blockchain))
    )
    
    buyer = format_address(transaction.get('buyer', 'Unknown'))
    seller = format_address(transaction.get('seller', 'Unknown'))
    
    # Build message
    if transaction_type.lower() == "sale":
        title = f"{emoji} New Sale Alert! {emoji}"
    else:
        title = f"{emoji} New Purchase Alert! {emoji}"
    
    message = f"{title}\n\n"
    message += f"Collection: {collection_name}\n"
    message += f"Blockchain: {blockchain}\n"
    message += f"NFT ID: #{token_id}\n"
    message += f"Price: {price}\n"
    message += f"Buyer: {buyer}\n"
    message += f"Seller: {seller}\n"
    
    if transaction.get('transaction_hash'):
        message += f"\nTransaction: {get_transaction_url(blockchain, transaction['transaction_hash'])}"
    
    return message

def get_blockchain_currency(blockchain):
    """Get the default currency for a blockchain"""
    blockchain_currencies = {
        "ethereum": "ETH",
        "solana": "SOL",
        "polygon": "MATIC"
    }
    return blockchain_currencies.get(blockchain.lower(), "Unknown")

def get_transaction_url(blockchain, transaction_hash):
    """Get the blockchain explorer URL for a transaction"""
    if not transaction_hash:
        return ""
    
    explorers = {
        "ethereum": f"https://etherscan.io/tx/{transaction_hash}",
        "solana": f"https://solscan.io/tx/{transaction_hash}",
        "polygon": f"https://polygonscan.com/tx/{transaction_hash}"
    }
    
    return explorers.get(blockchain.lower(), "#")
