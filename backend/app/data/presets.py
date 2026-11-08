"""Starter catalogues per business type (docs/08-inventory.md §1).

Items are added at price 0 for the owner to price. HSN codes are given only where they are
unambiguous; GST rates are left for the owner to choose because they depend on packaging/brand.
"""

# (name, category, unit, hsn)
PRESETS: dict[str, list[tuple[str, str, str, str | None]]] = {
    "grocery": [
        ("Rice", "Grains", "KGS", "1006"),
        ("Wheat Atta", "Grains", "KGS", "1101"),
        ("Sugar", "Essentials", "KGS", "1701"),
        ("Salt", "Essentials", "PAC", "2501"),
        ("Toor Dal", "Pulses", "KGS", "0713"),
        ("Sunflower Oil", "Oils", "LTR", "1512"),
        ("Tea Powder", "Beverages", "PAC", "0902"),
        ("Biscuits", "Snacks", "PAC", "1905"),
        ("Milk", "Dairy", "LTR", "0401"),
        ("Bath Soap", "Personal care", "NOS", "3401"),
    ],
    "apparel": [
        ("Shirt", "Men", "PCS", "6205"),
        ("T-Shirt", "Men", "PCS", "6109"),
        ("Jeans", "Men", "PCS", "6203"),
        ("Kurti", "Women", "PCS", "6204"),
        ("Saree", "Women", "PCS", None),
        ("Kids Frock", "Kids", "PCS", "6209"),
        ("Socks", "Accessories", "PRS", "6115"),
    ],
    "electronics": [
        ("Mobile Charger", "Accessories", "NOS", "8504"),
        ("USB Cable", "Accessories", "NOS", "8544"),
        ("Earphones", "Audio", "NOS", "8518"),
        ("Power Bank", "Accessories", "NOS", "8507"),
        ("Screen Guard", "Accessories", "NOS", "3919"),
        ("LED Bulb", "Lighting", "NOS", "8539"),
    ],
    "hardware": [
        ("Screws", "Fasteners", "BOX", "7318"),
        ("Nails", "Fasteners", "KGS", "7317"),
        ("PVC Pipe", "Plumbing", "MTR", "3917"),
        ("Wall Paint", "Paints", "LTR", "3209"),
        ("Hammer", "Tools", "NOS", "8205"),
        ("Electrical Wire", "Electrical", "MTR", "8544"),
    ],
    "stationery": [
        ("Ball Pen", "Writing", "NOS", "9608"),
        ("Pencil", "Writing", "NOS", "9609"),
        ("Notebook", "Paper", "NOS", "4820"),
        ("A4 Paper", "Paper", "PAC", "4802"),
        ("Eraser", "Writing", "NOS", "4016"),
        ("Glue Stick", "Craft", "NOS", "3506"),
    ],
    "pharmacy": [
        ("Paracetamol Tablets", "Medicines", "PAC", "3004"),
        ("Bandage", "First aid", "ROL", "3005"),
        ("Hand Sanitizer", "Hygiene", "BTL", "3808"),
        ("Face Mask", "Hygiene", "PAC", "6307"),
    ],
    "nursery": [  # PlantBill's starter list lives here now
        ("Rose Plant", "Flowering plants", "NOS", "0602"),
        ("Tulsi Plant", "Herbs", "NOS", "0602"),
        ("Money Plant", "Indoor plants", "NOS", "0602"),
        ("Aloe Vera", "Succulents", "NOS", "0602"),
        ("Snake Plant", "Indoor plants", "NOS", "0602"),
        ("Plastic Pot 8 inch", "Pots", "NOS", "3924"),
        ("Potting Mix", "Soil & manure", "BAG", "2530"),
        ("Vermicompost", "Soil & manure", "BAG", "3101"),
    ],
    "general": [
        ("Soap", "Personal care", "NOS", "3401"),
        ("Toothpaste", "Personal care", "NOS", "3306"),
        ("Biscuits", "Snacks", "PAC", "1905"),
        ("Notebook", "Stationery", "NOS", "4820"),
        ("Battery AA", "Electricals", "NOS", "8506"),
    ],
}
PRESETS["other"] = PRESETS["general"]
