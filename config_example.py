"""Constantes do marketplace NFT msu.io."""

# URLs
MAPLESTORY_BASE = "https://msu.io/"
MARKETPLACE_NFT_BASE = "https://msu.io/marketplace/nft"
MARKETPLACE_FT_BASE = "https://msu.io/marketplace/ft/"
CHARS_BASE = "https://msu.io/marketplace/character"

# NFTs
NFT_NAMES = []

# Google spreadsheets configuration
SPREADSHEET_ID = ""

# Metamask password
METAMASK_PASSWORD = ""

# Chrome settings
CHROME_USER_DATA_DIR = r""
CHROME_PROFILE_DIR = ""

# Metamask extension URL
METAMASK_EXTENSION_URL = ""

# Tracked NFTs
NFT_NAMES: list[str] = []

# Available FTs in the market and its IDs
FT_ITEMS: dict[str, int] = {}

# Tracked FTs
FT_NAMES: list[str] = []

# Chars and Jobs
CHARACTER_JOBS: dict[str, list[str]] = {}

SUBJOB_TO_SHEET = {}