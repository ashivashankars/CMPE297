"""Demo catalogue for 'GenAI Sports' (fictional). Mirrors the reference AlloyDB
schema: products, variants, stores, inventory, delivery methods, users."""

USERS = [  # (name, email, address, lat, lon)
    ("Alex Rivera", "alex@example.com", "100 Main St, Palo Alto, CA", 37.4419, -122.1430),
    ("Sam Taylor", "sam@example.com", "50 Market St, San Francisco, CA", 37.7936, -122.3965),
]

STORES = [  # (name, address, city, lat, lon)
    ("GenAI Sports Palo Alto", "180 El Camino Real", "Palo Alto", 37.4434, -122.1710),
    ("GenAI Sports San Jose", "925 Blossom Hill Rd", "San Jose", 37.2530, -121.8620),
    ("GenAI Sports San Francisco", "865 Market St", "San Francisco", 37.7840, -122.4070),
    ("GenAI Sports Oakland", "1 Broadway", "Oakland", 37.7955, -122.2770),
]

DELIVERY = [  # (name, description, cost, eta) - offered by every store
    ("Store Pickup", "Collect from the store counter", 0.00, "Same day"),
    ("Standard Home Delivery", "Ground shipping to your address", 5.99, "3-5 business days"),
    ("Express Delivery", "Priority courier", 14.99, "Next business day"),
]

# (name, brand, category, description, popularity, sizes, colors, price)
PRODUCTS = [
    ("Pegasus 41", "Nike", "Running", "Neutral daily running shoe with ReactX foam and Air Zoom units for a responsive, cushioned ride.", 0.95, ["8", "9", "10", "11"], ["Black/White", "Blue"], 139.99),
    ("Glycerin 22", "Brooks", "Running", "Plush max-cushion road running shoe with DNA Tuned nitrogen-infused foam for long easy miles.", 0.88, ["8", "9", "10", "11", "12"], ["Grey/Orange", "Black"], 164.99),
    ("Clifton 10", "Hoka", "Running", "Lightweight cushioned trainer with a rocker sole; great for beginners and recovery runs.", 0.90, ["7", "8", "9", "10", "11"], ["White", "Black/Gold"], 149.99),
    ("Speedgoat 6", "Hoka", "Trail Running", "Grippy trail running shoe with Vibram Megagrip outsole for technical mountain terrain.", 0.86, ["8", "9", "10", "11"], ["Green", "Black"], 154.99),
    ("Ultraboost 5", "Adidas", "Running", "Energy-returning Boost foam running shoe with a Primeknit upper; comfortable for running and walking.", 0.84, ["8", "9", "10", "11"], ["Core Black", "Cloud White"], 189.99),
    ("Gel-Kayano 31", "ASICS", "Running", "Stability running shoe for overpronation with FF BLAST+ foam and 4D Guidance System.", 0.83, ["8", "9", "10", "11", "12"], ["Blue/Silver", "Black"], 164.99),
    ("Atmos AG 65", "Osprey", "Hiking", "65L backpacking pack with Anti-Gravity mesh suspension for multi-day hikes with heavy loads.", 0.80, ["S/M", "L/XL"], ["Mythical Green", "Black"], 349.95),
    ("Talon 22", "Osprey", "Hiking", "22L lightweight day-hiking backpack with hydration sleeve and trekking pole attachment.", 0.78, ["S/M", "L/XL"], ["Ceramic Blue", "Black"], 169.95),
    ("Hydro Flask 32oz", "Hydro Flask", "Accessories", "Insulated stainless steel water bottle that keeps drinks cold for 24 hours.", 0.75, ["32oz"], ["Black", "Pacific", "White"], 44.95),
    ("Dri-FIT Running Tee", "Nike", "Apparel", "Sweat-wicking lightweight running T-shirt with reflective details.", 0.70, ["S", "M", "L", "XL"], ["Black", "Volt"], 35.00),
    ("Tiro 24 Training Pants", "Adidas", "Apparel", "Slim training pants with zip pockets for football practice and the gym.", 0.72, ["S", "M", "L", "XL"], ["Black/White", "Navy"], 50.00),
    ("Mercurial Vapor 16 Elite", "Nike", "Football", "Elite firm-ground football boot built for speed with a Zoom Air unit.", 0.82, ["8", "9", "10", "11"], ["Pink/Black", "Silver"], 284.99),
    ("Predator Elite FG", "Adidas", "Football", "Control football boot with rubber grip fins for passing and shooting accuracy.", 0.81, ["8", "9", "10", "11"], ["Core Black/Red", "White"], 269.99),
    ("Official Match Ball", "Adidas", "Football", "FIFA Quality Pro match ball with thermally bonded panels.", 0.74, ["5"], ["White/Blue"], 165.00),
    ("Pro Staff 97", "Wilson", "Tennis", "Classic control-oriented tennis racquet, 97 sq in head, 315g unstrung.", 0.69, ["Grip 2", "Grip 3", "Grip 4"], ["Black"], 269.00),
    ("Pure Aero", "Babolat", "Tennis", "Spin-friendly tennis racquet favoured by baseline players, 100 sq in head.", 0.73, ["Grip 2", "Grip 3", "Grip 4"], ["Yellow/Black"], 279.00),
    ("Yoga Mat 5mm", "Manduka", "Fitness", "Non-slip 5mm yoga and pilates mat made from natural rubber.", 0.68, ["Standard"], ["Black Magic", "Purple"], 89.00),
    ("Adjustable Dumbbells 52.5lb", "Bowflex", "Fitness", "Space-saving adjustable dumbbell pair, 5 to 52.5 lb per hand.", 0.77, ["Pair"], ["Black"], 429.00),
    ("Fenix 8 GPS Watch", "Garmin", "Electronics", "Multisport GPS smartwatch with heart rate, maps and 16-day battery for running, cycling, hiking.", 0.85, ["47mm", "51mm"], ["Slate Grey"], 999.99),
    ("Trail Running Vest 5L", "Salomon", "Trail Running", "Lightweight 5L hydration vest with soft flasks for ultra and trail races.", 0.71, ["S", "M", "L"], ["Black", "Blue"], 145.00),
]
