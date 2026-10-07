"""Central configuration: paths, Spark settings and every tunable threshold."""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
RAW_ZIP = DATA_RAW / "online_retail_ii.zip"
RAW_XLSX = DATA_RAW / "online_retail_II.xlsx"
RAW_CSV = DATA_RAW / "online_retail_II.csv"
DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"

OUT = ROOT / "outputs"
BRONZE = OUT / "bronze" / "transactions"
SILVER = OUT / "silver" / "transactions"
SILVER_CANCELLED = OUT / "silver" / "cancellations"
GOLD_FEATURES = OUT / "gold" / "customer_features"
EDA_DIR = OUT / "eda"
CHARTS_DIR = OUT / "charts"
MODELS_DIR = OUT / "models"
FINAL_DIR = OUT / "final"

# ---------------------------------------------------------------- spark
SPARK_APP_NAME = "OnlineRetailCustomerIntelligence"
SPARK_MASTER = "local[*]"
SPARK_CONF = {
    "spark.driver.memory": "6g",
    "spark.sql.shuffle.partitions": "16",
    "spark.sql.session.timeZone": "UTC",
    "spark.ui.showConsoleProgress": "false",
}

# ---------------------------------------------------------------- cleaning
# StockCodes that are fees, postage, adjustments or test entries rather than products
NON_PRODUCT_CODES = [
    "POST", "DOT", "M", "D", "C2", "C3", "S", "B", "CRUK", "PADS", "ADJUST", "ADJUST2",
    "BANK CHARGES", "AMAZONFEE", "SP1002", "GIFT",
]
NON_PRODUCT_PREFIXES = ["TEST", "GIFT_", "DCGS"]

# ---------------------------------------------------------------- features
FEATURE_COLS = [
    "Recency", "Frequency", "Monetary", "AvgOrderValue", "TotalItems",
    "UniqueProducts", "AvgQuantityPerOrder", "ActiveMonths", "TenureDays",
    "AvgDaysBetweenOrders", "CancellationRate",
]
# Features fed to K-Means. Skewed ones get log1p before scaling.
CLUSTER_FEATURES = [
    "Recency", "Frequency", "Monetary", "AvgOrderValue",
    "UniqueProducts", "ActiveMonths", "CancellationRate",
]
LOG_FEATURES = ["Recency", "Frequency", "Monetary", "AvgOrderValue", "UniqueProducts", "ActiveMonths"]

# ---------------------------------------------------------------- clustering
K_RANGE = list(range(2, 9))
K_BUSINESS_RANGE = (4, 6)          # interpretable number of segments
SEED = 42
KMEANS_MAX_ITER = 50

# ---------------------------------------------------------------- scoring
CVS_WEIGHTS = {"M": 0.4, "F": 0.3, "R": 0.3}
VALUE_BANDS = [(80, "Very High"), (60, "High"), (40, "Medium"), (20, "Low"), (0, "Very Low")]
CHURN_INACTIVE_DAYS = 90           # no purchase in a quarter = inactive
CHURN_MIN_GAP_DAYS = 30            # floor for a customer's typical purchase gap
CHURN_OVERDUE_HIGH = 2.0           # 2x overdue vs own rhythm -> high risk
CHURN_OVERDUE_MEDIUM = 1.5
CHURN_HIGH_VALUE_CVS = 60

# ---------------------------------------------------------------- market basket
FP_MIN_SUPPORT = 0.01
FP_MIN_CONFIDENCE = 0.2
FP_TARGET_RULES = (100, 500)
FP_SUPPORT_LADDER = [0.02, 0.015, 0.01, 0.0075, 0.005]
TOP_N_PRODUCT_RECS = 3

# Keyword -> category heuristic (dataset has no category column). First match wins; keywords
# match at the start of a word, so order matters ("TEA LIGHT" must hit Lighting before Kitchen).
CATEGORY_KEYWORDS = [
    ("Christmas & Seasonal", ["CHRISTMAS", "XMAS", "ADVENT", "EASTER", "SANTA", "REINDEER", "SNOWFLAKE"]),
    ("Lighting & Candles", ["CANDLE", "LIGHT", "LANTERN", "T-LIGHT", "LAMP", "TEALIGHT"]),
    ("Kitchen & Dining", ["MUG", "CUP", "PLATE", "BOWL", "TEA", "CAKE", "BAKING", "KITCHEN", "SPOON", "NAPKIN", "LUNCH", "BOTTLE", "TRAY", "JAM", "CUTLERY"]),
    ("Bags & Storage", ["BAG", "BOX", "TIN", "STORAGE", "BASKET", "JAR", "HOLDER", "CASE"]),
    ("Stationery & Gift Wrap", ["CARD", "WRAP", "PAPER", "NOTEBOOK", "PEN", "PENCIL", "STICKER", "TAPE", "RIBBON", "ENVELOPE", "CHALKBOARD"]),
    ("Toys & Kids", ["TOY", "DOLL", "GAME", "CHILDREN", "KIDS", "PARTY", "BALLOON", "SPACEBOY", "DOLLY", "JIGSAW"]),
    ("Garden & Outdoor", ["GARDEN", "PLANT", "FLOWER", "BIRD", "WATERING"]),
    ("Fashion & Accessories", ["NECKLACE", "BRACELET", "EARRINGS", "RING", "HAIR", "PURSE", "UMBRELLA", "SCARF"]),
    ("Home Decor", ["SIGN", "FRAME", "DECORATION", "HEART", "CLOCK", "MIRROR", "CUSHION", "WALL", "HANGING", "ORNAMENT", "DOORMAT", "VINTAGE", "BUNTING"]),
]
DEFAULT_CATEGORY = "Other"

for _d in (DATA_RAW, EDA_DIR, CHARTS_DIR, MODELS_DIR, FINAL_DIR):
    _d.mkdir(parents=True, exist_ok=True)
