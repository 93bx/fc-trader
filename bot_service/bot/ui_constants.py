"""
FC Companion UI selectors. Prefer resource-id, then content-desc, then text (per .cursorrules §5).
Update these after capturing real hierarchy via adb shell uiautomator dump / inspector.
"""

# Search filters — use text as fallback until real resourceIds are set from dump
SEARCH_PLAYER_NAME = {"text": "Player Name"}
SEARCH_QUALITY = {"text": "Quality"}
SEARCH_POSITION = {"text": "Position"}
SEARCH_MAX_BUY_NOW = {"text": "Max Buy Now"}
SEARCH_CHEMISTRY_STYLE = {"text": "Chemistry Style"}
SEARCH_BUTTON = {"text": "Search"}

# Landmarks
TEXT_SEARCH_FILTERS = "Search Filters"
TEXT_TRANSFERS = "Transfers"
TEXT_TRANSFER_MARKET = "Transfer Market"
TEXT_CLUB = "Club"
TEXT_BUY_NOW = "Buy Now"
TEXT_CONFIRM = "Confirm"
TEXT_BID = "Bid"
