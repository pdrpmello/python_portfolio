"""Constantes do marketplace NFT msu.io."""

# URLs
MAPLESTORY_BASE = "https://msu.io/"
MARKETPLACE_NFT_BASE = "https://msu.io/marketplace/nft"
MARKETPLACE_FT_BASE = "https://msu.io/marketplace/ft/"
CHARS_BASE = "https://msu.io/marketplace/character"

# NFTs
NFT_NAMES = []

# Google spreadsheets configuration
SPREADSHEET_ID = "17WBynjxpo2XP3o0DCEnxkbxaxczZuwy78UxqANazgG8"

# Metamask password
METAMASK_PASSWORD = "PedroA320!"

# Chrome settings
CHROME_USER_DATA_DIR = r"C:\chrome-selenium-profile"
CHROME_PROFILE_DIR = "Default"

# Metamask extension URL
METAMASK_EXTENSION_URL = "chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/notification.html"

# Tracked NFTs
NFT_NAMES: list[str] = [
    "Neophyte Ring",
    "Fafnir Damascus",
    "Seven Days Badge",
    "Twilight Mark",
    "Shooting Star",
    "Absolab Bandit Cape",
    "Absolab Thief Shoulder",
    "Absolab Bandit Shoes",
    "Absolab Blade Lord",
    "Absolab Bandit Gloves",
    "Eagle Eye Assassin Shirt",
    "Trixter Assassin Pants",
    "Absolab Pirate Cape",
    "Absolab Pirate Shoes",
    "Absolab Pirate Shoulder",
    "Fafnir Zeliska",
    "Eagle Eye Wanderer Coat",
    "Trixter Wanderer Pants",
]

# Available FTs in the market and its IDs
FT_ITEMS: dict[str, int] = {
    "Umushroom Coupon (100-Day)": 2358000,
    "King Pengu Coupon (100-Day)": 2358006,
    "Green Florin": 4310401,
    "Fragment of Kaiserium": 4310397,
    "Phantasma Coin": 4310218,
    "Life Coin": 4310420,
    "Blue Florin": 4310402,
    "AbsoLab Coin": 4310156,
    "Stigma Coin": 4310199,
    "Gold Florin": 4310404,
    "Sealed Nodestone": 2358005,
    "Red Florin": 4310403,
    "Super Hasty Hunting Booster Package Coupon": 2358008,
    "Purified Chaos Yggdrasil Energy": 4310396,
}

# Tracked FTs
FT_NAMES: list[str] = [
    "Purified Chaos Yggdrasil Energy",
    "Sealed Nodestone",
    "Phantasma Coin",
    "Red Florin",
    "AbsoLab Coin",
    "Gold Florin",
    "Stigma Coin",
]

# Chars and Jobs
CHARACTER_JOBS: dict[str, list[str]] = {
    "warrior": ["hero", "paladin", "dark_knight", "aran", "dawn_warrior", "mihile"],
    "magician": ["evan", "luminous", "blaze_wizard", "arch_mage_fp", "arch_mage_il", "bishop"],
    "bowman": ["bowmaster", "marksman", "mercedes", "wind_archer", "pathfinder"],
    "thief": ["night_lord", "shadower", "phantom", "night_walker", "blademaster"],
    "pirate": ["buccaneer", "corsair", "shade", "thunder_breaker", "cannonmaster"],
}

SUBJOB_TO_SHEET = {
    "hero": "Hero",
    "paladin": "Paladin",
    "dark_knight": "Dark Knight",
    "aran": "Aran",
    "dawn_warrior": "Dawn Warrior",
    "mihile": "Mihile",

    "evan": "Evan",
    "luminous": "Luminous",
    "blaze_wizard": "Blaze Wizard",
    "arch_mage_fp": "Arch Mage F/P",
    "arch_mage_il": "Arch Mage I/L",
    "bishop": "Bishop",

    "bowmaster": "Bowmaster",
    "marksman": "Marksman",
    "mercedes": "Mercedes",
    "wind_archer": "Wind Archer",
    "pathfinder": "Pathfinder",

    "night_lord": "Night Lord",
    "shadower": "Shadower",
    "phantom": "Phantom",
    "night_walker": "Night Walker",
    "blademaster": "Blademaster",

    "buccaneer": "Buccaneer",
    "corsair": "Corsair",
    "shade": "Shade",
    "thunder_breaker": "Thunder Breaker",
    "cannonmaster": "Cannonmaster",
}