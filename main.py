import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
import database as db
from handlers import (
    start,
    help_command,
    add_collection_start,
    blockchain_selected,
    marketplace_selected,
    collection_address_entered,
    cancel,
    list_collections,
    remove_collection_start,
    remove_collection_selected,
    settings_start,
    settings_option_selected,
    alert_type_selected,
    update_frequency_selected,
    send_transaction_alert,
    BLOCKCHAIN_SELECTION,
    MARKETPLACE_SELECTION,
    COLLECTION_ADDRESS,
    SETTINGS_ALERT_TYPE,
    SETTINGS_UPDATE_FREQUENCY,
    REMOVE_COLLECTION_SELECTION
)
from nft_trackers import get_tracker
from utils import get_current_timestamp, parse_timestamp

logger = logging.getLogger(__name__)

async def check_for_new_transactions(context):
    """Background task to check for new transactions"""
    application = context.application
    tracked_collections = db.get_all_tracked_collections()
    
    if not tracked_collections:
        logger.info("No collections being tracked")
        return
    
    for collection in tracked_collections:
        blockchain = collection["blockchain"]
        marketplace = collection["marketplace"]
        collection_address = collection["collection_address"]
        
        # Get the appropriate tracker
        tracker = get_tracker(blockchain, marketplace)
        if not tracker:
            logger.warning(f"No tracker found for {blockchain}/{marketplace}")
            continue
        
        try:
            # Get recent transactions
            transactions = tracker.get_recent_transactions(collection_address)
            
            if not transactions:
                logger.info(f"No new transactions for {collection_address} on {blockchain}")
                continue
            
            logger.info(f"Found {len(transactions)} new transactions for {collection_address} on {blockchain}")
            
            # Get collection info for the alert message
            collection_info = tracker.get_collection_info(collection_address)
            
            # Get users tracking this collection
            trackers = db.get_collection_trackers(blockchain, collection_address)
            
            # Send alerts to users
            for transaction in transactions:
                for tracker_info in trackers:
                    user_id = tracker_info["user_id"]
                    settings = tracker_info["settings"]
                    
                    # Filter based on user settings
                    alert_type = settings.get("alert_type", "all")
                    if alert_type != "all":
                        transaction_type = transaction.get("transaction_type", "").lower()
                        if alert_type == "sales" and transaction_type != "sale":
                            continue
                        if alert_type == "purchases" and transaction_type != "purchase":
                            continue
                    
                    # Send the alert
                    await send_transaction_alert(context, user_id, transaction, collection_info)
        
        except Exception as e:
            logger.error(f"Error checking transactions for {collection_address} on {blockchain}: {e}")

def get_scheduler_jobs():
    """Configure scheduler jobs based on different update frequencies"""
    return [
        {
            "id": "check_instant",
            "func": check_for_new_transactions,
            "trigger": IntervalTrigger(seconds=config.POLLING_INTERVALS["instant"]),
            "name": "Check for new transactions (instant)"
        },
        {
            "id": "check_10min",
            "func": check_for_new_transactions,
            "trigger": IntervalTrigger(seconds=config.POLLING_INTERVALS["10min"]),
            "name": "Check for new transactions (10min)"
        },
        {
            "id": "check_hourly",
            "func": check_for_new_transactions,
            "trigger": IntervalTrigger(seconds=config.POLLING_INTERVALS["hourly"]),
            "name": "Check for new transactions (hourly)"
        }
    ]

def main():
    """Start the bot"""
    # Initialize database
    db.init_db()
    
    # Create the application
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Add conversation handlers
    add_collection_handler = ConversationHandler(
        entry_points=[CommandHandler("addcollection", add_collection_start)],
        states={
            BLOCKCHAIN_SELECTION: [CallbackQueryHandler(blockchain_selected)],
            MARKETPLACE_SELECTION: [CallbackQueryHandler(marketplace_selected)],
            COLLECTION_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collection_address_entered)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$")
        ]
    )
    
    remove_collection_handler = ConversationHandler(
        entry_points=[CommandHandler("removecollection", remove_collection_start)],
        states={
            REMOVE_COLLECTION_SELECTION: [CallbackQueryHandler(remove_collection_selected)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$")
        ]
    )
    
    settings_handler = ConversationHandler(
        entry_points=[CommandHandler("settings", settings_start)],
        states={
            SETTINGS_ALERT_TYPE: [
                CallbackQueryHandler(settings_option_selected, pattern="^settings:"),
                CallbackQueryHandler(alert_type_selected, pattern="^alert_type:")
            ],
            SETTINGS_UPDATE_FREQUENCY: [CallbackQueryHandler(update_frequency_selected, pattern="^frequency:")]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$")
        ]
    )
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("listcollections", list_collections))
    application.add_handler(add_collection_handler)
    application.add_handler(remove_collection_handler)
    application.add_handler(settings_handler)
    
    # Set up the scheduler
    scheduler = AsyncIOScheduler()
    
    # Add jobs to the scheduler
    for job in get_scheduler_jobs():
        scheduler.add_job(
            job["func"],
            trigger=job["trigger"],
            id=job["id"],
            name=job["name"],
            args=[application]
        )
    
    # Start the scheduler
    scheduler.start()
    
    # Run the bot
    application.run_polling()
    
    # Stop the scheduler when the bot stops
    scheduler.shutdown()

if __name__ == "__main__":
    main()
