import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database as db
from nft_trackers import get_tracker
from utils import (
    validate_ethereum_address, 
    validate_solana_address, 
    format_transaction_alert
)

logger = logging.getLogger(__name__)

# Conversation states
BLOCKCHAIN_SELECTION, MARKETPLACE_SELECTION, COLLECTION_ADDRESS = range(3)
SETTINGS_ALERT_TYPE, SETTINGS_UPDATE_FREQUENCY = range(3, 5)
REMOVE_COLLECTION_SELECTION = 5

# Helper dictionaries
BLOCKCHAINS = {
    "ethereum": "Ethereum",
    "solana": "Solana",
    "polygon": "Polygon"
}

MARKETPLACES = {
    "ethereum": ["opensea", "blur", "looksrare"],
    "solana": ["magiceden", "tensor"],
    "polygon": ["opensea", "okx"]
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    user = update.effective_user
    db.add_user(user.id, user.first_name, user.username)
    
    welcome_text = (
        f"Hello {user.first_name}! 👋\n\n"
        "Welcome to the NFT Transaction Tracker Bot. "
        "I can help you track NFT sales and purchases across multiple blockchains and marketplaces.\n\n"
        "Here are the commands you can use:\n"
        "/addcollection - Start tracking an NFT collection\n"
        "/removecollection - Stop tracking a collection\n"
        "/listcollections - Show your tracked collections\n"
        "/settings - Customize your alert preferences\n"
        "/help - Show this help message"
    )
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command"""
    help_text = (
        "NFT Transaction Tracker Bot - Help\n\n"
        "Available commands:\n"
        "/start - Start the bot and see welcome message\n"
        "/addcollection - Add an NFT collection to track\n"
        "/removecollection - Stop tracking a collection\n"
        "/listcollections - Show all collections you're tracking\n"
        "/settings - Customize your alert preferences\n"
        "/help - Show this help message\n\n"
        "How it works:\n"
        "1. Add collections you want to track using /addcollection\n"
        "2. You'll receive alerts when NFTs in those collections are bought or sold\n"
        "3. Use /settings to customize what types of alerts you receive"
    )
    
    await update.message.reply_text(help_text)

async def add_collection_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the add collection conversation"""
    keyboard = [
        [InlineKeyboardButton("Ethereum", callback_data="blockchain:ethereum")],
        [InlineKeyboardButton("Solana", callback_data="blockchain:solana")],
        [InlineKeyboardButton("Polygon", callback_data="blockchain:polygon")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Which blockchain does the NFT collection use?",
        reply_markup=reply_markup
    )
    
    return BLOCKCHAIN_SELECTION

async def blockchain_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle blockchain selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    
    # Extract blockchain from callback data
    _, blockchain = query.data.split(":")
    context.user_data["add_collection_blockchain"] = blockchain
    
    # Generate marketplace buttons based on the selected blockchain
    keyboard = []
    for marketplace in MARKETPLACES.get(blockchain, []):
        keyboard.append([InlineKeyboardButton(
            marketplace.capitalize(), 
            callback_data=f"marketplace:{marketplace}"
        )])
    
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected blockchain: {BLOCKCHAINS.get(blockchain)}\n"
        f"Which marketplace does the collection use?",
        reply_markup=reply_markup
    )
    
    return MARKETPLACE_SELECTION

async def marketplace_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle marketplace selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    
    # Extract marketplace from callback data
    _, marketplace = query.data.split(":")
    context.user_data["add_collection_marketplace"] = marketplace
    
    blockchain = context.user_data.get("add_collection_blockchain")
    
    await query.edit_message_text(
        f"Selected blockchain: {BLOCKCHAINS.get(blockchain)}\n"
        f"Selected marketplace: {marketplace.capitalize()}\n\n"
        f"Please enter the collection address or identifier:"
    )
    
    return COLLECTION_ADDRESS

async def collection_address_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle collection address entry"""
    collection_address = update.message.text.strip()
    blockchain = context.user_data.get("add_collection_blockchain")
    marketplace = context.user_data.get("add_collection_marketplace")
    
    # Validate the collection address format
    is_valid_format = True
    if blockchain == "ethereum" or blockchain == "polygon":
        is_valid_format = validate_ethereum_address(collection_address)
    elif blockchain == "solana":
        is_valid_format = validate_solana_address(collection_address) or len(collection_address) > 0
    
    if not is_valid_format:
        await update.message.reply_text(
            f"Invalid collection address format for {BLOCKCHAINS.get(blockchain)}. "
            f"Please try again or use /cancel to cancel."
        )
        return COLLECTION_ADDRESS
    
    # Get the appropriate tracker
    tracker = get_tracker(blockchain, marketplace)
    if not tracker:
        await update.message.reply_text(
            f"Sorry, tracking for {marketplace.capitalize()} on {BLOCKCHAINS.get(blockchain)} "
            f"is not supported yet. Please try a different combination."
        )
        return ConversationHandler.END
    
    # Show a processing message
    processing_message = await update.message.reply_text("Validating collection... Please wait.")
    
    # Validate that the collection exists
    is_valid_collection = tracker.validate_collection(collection_address)
    
    if not is_valid_collection:
        await processing_message.edit_text(
            f"Could not find a valid collection at the address/symbol provided. "
            f"Please check your input and try again."
        )
        return COLLECTION_ADDRESS
    
    # Get collection info to get the name
    collection_info = tracker.get_collection_info(collection_address)
    collection_name = collection_info.get("collection_name") if collection_info else None
    
    # Add to database
    user_id = update.effective_user.id
    success = db.add_collection(
        user_id=user_id,
        blockchain=blockchain,
        marketplace=marketplace,
        collection_address=collection_address,
        collection_name=collection_name
    )
    
    if success:
        await processing_message.edit_text(
            f"✅ Successfully added collection {collection_name or collection_address} "
            f"on {BLOCKCHAINS.get(blockchain)} ({marketplace.capitalize()}).\n\n"
            f"You will now receive alerts when NFTs in this collection are bought or sold."
        )
    else:
        await processing_message.edit_text(
            f"You're already tracking {collection_name or collection_address} "
            f"on {BLOCKCHAINS.get(blockchain)}."
        )
    
    # Clear conversation data
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation"""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operation cancelled.")
    else:
        await update.message.reply_text("Operation cancelled.")
    
    # Clear conversation data
    context.user_data.clear()
    
    return ConversationHandler.END

async def list_collections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /listcollections command"""
    user_id = update.effective_user.id
    collections = db.get_user_collections(user_id)
    
    if not collections:
        await update.message.reply_text(
            "You're not tracking any collections yet. "
            "Use /addcollection to start tracking an NFT collection."
        )
        return
    
    message = "🔍 Your tracked collections:\n\n"
    
    for i, collection in enumerate(collections, 1):
        blockchain = collection.get("blockchain", "Unknown")
        marketplace = collection.get("marketplace", "Unknown")
        address = collection.get("collection_address", "Unknown")
        name = collection.get("collection_name") or address
        
        message += (
            f"{i}. {name}\n"
            f"   • Blockchain: {BLOCKCHAINS.get(blockchain, blockchain)}\n"
            f"   • Marketplace: {marketplace.capitalize()}\n"
            f"   • Address: {address}\n\n"
        )
    
    message += "To stop tracking a collection, use /removecollection"
    
    await update.message.reply_text(message)

async def remove_collection_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the remove collection conversation"""
    user_id = update.effective_user.id
    collections = db.get_user_collections(user_id)
    
    if not collections:
        await update.message.reply_text(
            "You're not tracking any collections yet. "
            "Use /addcollection to start tracking an NFT collection."
        )
        return ConversationHandler.END
    
    keyboard = []
    
    # Store collections in context for later reference
    context.user_data["remove_collections"] = collections
    
    for i, collection in enumerate(collections):
        name = collection.get("collection_name") or collection.get("collection_address")
        blockchain = collection.get("blockchain")
        keyboard.append([InlineKeyboardButton(
            f"{name} ({BLOCKCHAINS.get(blockchain, blockchain)})",
            callback_data=f"remove:{i}"
        )])
    
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a collection to remove from tracking:",
        reply_markup=reply_markup
    )
    
    return REMOVE_COLLECTION_SELECTION

async def remove_collection_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle collection selection for removal"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    
    # Extract collection index from callback data
    _, index = query.data.split(":")
    index = int(index)
    
    collections = context.user_data.get("remove_collections", [])
    if not collections or index >= len(collections):
        await query.edit_message_text("Error: Collection not found.")
        return ConversationHandler.END
    
    selected_collection = collections[index]
    user_id = update.effective_user.id
    
    # Remove from database
    success = db.remove_collection(
        user_id=user_id,
        blockchain=selected_collection.get("blockchain"),
        collection_address=selected_collection.get("collection_address")
    )
    
    if success:
        name = selected_collection.get("collection_name") or selected_collection.get("collection_address")
        blockchain = selected_collection.get("blockchain")
        
        await query.edit_message_text(
            f"✅ Successfully removed {name} on {BLOCKCHAINS.get(blockchain, blockchain)} "
            f"from tracking."
        )
    else:
        await query.edit_message_text("Error: Failed to remove collection.")
    
    # Clear conversation data
    context.user_data.clear()
    
    return ConversationHandler.END

async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the settings conversation"""
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)
    
    # Store current settings for reference
    context.user_data["current_settings"] = settings
    
    keyboard = [
        [InlineKeyboardButton("Alert Types", callback_data="settings:alert_type")],
        [InlineKeyboardButton("Update Frequency", callback_data="settings:frequency")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    
    current_alert_type = settings.get("alert_type", "all")
    current_frequency = settings.get("update_frequency", "instant")
    
    alert_type_display = {
        "all": "All transactions",
        "sales": "Sales only",
        "purchases": "Purchases only"
    }
    
    frequency_display = {
        "instant": "Instant alerts",
        "10min": "Every 10 minutes",
        "hourly": "Hourly updates"
    }
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ Settings\n\n"
        f"Current alert type: {alert_type_display.get(current_alert_type)}\n"
        f"Current update frequency: {frequency_display.get(current_frequency)}\n\n"
        "What would you like to change?",
        reply_markup=reply_markup
    )
    
    return SETTINGS_ALERT_TYPE

async def settings_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings option selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Settings unchanged.")
        return ConversationHandler.END
    
    # Extract setting type from callback data
    _, setting_type = query.data.split(":")
    
    if setting_type == "alert_type":
        keyboard = [
            [InlineKeyboardButton("All Transactions", callback_data="alert_type:all")],
            [InlineKeyboardButton("Sales Only", callback_data="alert_type:sales")],
            [InlineKeyboardButton("Purchases Only", callback_data="alert_type:purchases")],
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select which types of alerts you want to receive:",
            reply_markup=reply_markup
        )
        
        return SETTINGS_ALERT_TYPE
        
    elif setting_type == "frequency":
        keyboard = [
            [InlineKeyboardButton("Instant Alerts", callback_data="frequency:instant")],
            [InlineKeyboardButton("Every 10 Minutes", callback_data="frequency:10min")],
            [InlineKeyboardButton("Hourly Updates", callback_data="frequency:hourly")],
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select how often you want to receive updates:",
            reply_markup=reply_markup
        )
        
        return SETTINGS_UPDATE_FREQUENCY

async def alert_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle alert type selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Settings unchanged.")
        return ConversationHandler.END
    
    # Extract alert type from callback data
    _, alert_type = query.data.split(":")
    
    # Update settings
    user_id = update.effective_user.id
    current_settings = context.user_data.get("current_settings", {})
    current_settings["alert_type"] = alert_type
    
    db.update_user_settings(user_id, current_settings)
    
    alert_type_display = {
        "all": "All transactions",
        "sales": "Sales only",
        "purchases": "Purchases only"
    }
    
    await query.edit_message_text(
        f"✅ Alert type updated to: {alert_type_display.get(alert_type)}"
    )
    
    # Clear conversation data
    context.user_data.clear()
    
    return ConversationHandler.END

async def update_frequency_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle update frequency selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Settings unchanged.")
        return ConversationHandler.END
    
    # Extract frequency from callback data
    _, frequency = query.data.split(":")
    
    # Update settings
    user_id = update.effective_user.id
    current_settings = context.user_data.get("current_settings", {})
    current_settings["update_frequency"] = frequency
    
    db.update_user_settings(user_id, current_settings)
    
    frequency_display = {
        "instant": "Instant alerts",
        "10min": "Every 10 minutes",
        "hourly": "Hourly updates"
    }
    
    await query.edit_message_text(
        f"✅ Update frequency updated to: {frequency_display.get(frequency)}"
    )
    
    # Clear conversation data
    context.user_data.clear()
    
    return ConversationHandler.END

async def send_transaction_alert(context: ContextTypes.DEFAULT_TYPE, user_id, transaction, collection_info=None):
    """Send a transaction alert to a user"""
    try:
        message = format_transaction_alert(transaction, collection_info)
        await context.bot.send_message(chat_id=user_id, text=message)
        logger.info(f"Alert sent to user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert to user {user_id}: {e}")
        return False
