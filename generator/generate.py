"""Generate JaiDee Mart raw tables."""

import argparse
import csv
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

BANGKOK = ZoneInfo("Asia/Bangkok")
START_DATE = date(2025, 4, 1)
END_DATE = date(2026, 9, 30)
VAT_RATE = Decimal("0.07")

SCALES = {
    "teaching": {"customers": 2500, "orders": 12000},
    "large": {"customers": 25000, "orders": 120000},
}

TABLE_NAMES = (
    "customers",
    "orders",
    "order_items",
    "products",
    "stores",
    "deliveries",
    "payments",
    "reviews",
)

COLUMNS = {
    "customers": [
        "customer_id",
        "full_name",
        "email",
        "phone",
        "region",
        "province",
        "channel",
        "created_at",
    ],
    "orders": [
        "order_id",
        "customer_id",
        "store_id",
        "order_placed_at",
        "recorded_at",
        "status",
        "subtotal_thb",
        "discount_thb",
        "tax_thb",
        "delivery_fee_thb",
        "order_total_thb",
    ],
    "order_items": [
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price_thb",
        "unit_cost_thb",
        "line_total_thb",
    ],
    "products": [
        "product_id",
        "sku",
        "product_name",
        "category",
        "unit_price_thb",
        "unit_cost_thb",
    ],
    "stores": [
        "store_id",
        "store_name",
        "region",
        "province",
        "opened_on",
    ],
    "deliveries": [
        "delivery_id",
        "order_id",
        "promised_at",
        "delivered_at",
        "status",
        "recorded_at",
    ],
    "payments": [
        "payment_id",
        "order_id",
        "paid_at",
        "method",
        "status",
        "amount_thb",
        "recorded_at",
    ],
    "reviews": [
        "review_id",
        "order_id",
        "customer_id",
        "reviewed_at",
        "score",
        "recorded_at",
    ],
}

REGIONS = ["Bangkok", "Central", "North", "Northeast", "South"]
REGION_WEIGHTS = [34, 18, 16, 18, 14]
PROVINCES = {
    "Bangkok": ["Bangkok"],
    "Central": ["Ayutthaya", "Nonthaburi", "Samut Prakan", "Nakhon Pathom"],
    "North": ["Chiang Mai", "Chiang Rai", "Lampang"],
    "Northeast": ["Khon Kaen", "Nakhon Ratchasima", "Udon Thani", "Ubon Ratchathani"],
    "South": ["Phuket", "Songkhla", "Surat Thani", "Nakhon Si Thammarat"],
}

CHANNELS = ["line", "web", "facebook", "phone", "walk_in"]
CHANNEL_WEIGHTS = [30, 24, 18, 14, 14]
CHANNEL_ORDER_WEIGHT = {
    "line": 4.0,
    "web": 2.4,
    "facebook": 1.8,
    "phone": 1.1,
    "walk_in": 0.7,
}

METHODS = ["promptpay", "cash_on_delivery", "credit_card", "truemoney", "bank_transfer"]
METHOD_WEIGHTS = [42, 28, 12, 10, 8]

HOUR_WEIGHTS = [
    1, 1, 1, 1, 1, 2,
    3, 4,
    5, 6, 7, 8, 8, 7, 6, 6, 7, 9, 11, 10,
    7, 5, 3, 2,
]

REGION_CATEGORY_BIAS = {
    "Bangkok": {"snacks": 1.8, "beverages": 1.7, "household": 1.4, "frozen": 1.3},
    "Central": {"vegetables": 1.5, "fruit": 1.4, "rice_and_noodles": 1.2},
    "North": {"fruit": 1.6, "vegetables": 1.4, "pantry": 1.3},
    "Northeast": {"rice_and_noodles": 1.8, "pantry": 1.5, "meat_and_seafood": 1.2},
    "South": {"meat_and_seafood": 1.7, "fruit": 1.4, "beverages": 1.3},
}

PROMISE_MINUTES = {
    "Bangkok": 50,
    "Central": 120,
    "North": 180,
    "Northeast": 180,
    "South": 200,
}

# sku, name, category, price baht, margin rate
CATALOG = [
    ("JD-FRU-001", "Nam Dok Mai mango", "fruit", "45.00", "0.32"),
    ("JD-FRU-002", "Banana", "fruit", "29.00", "0.28"),
    ("JD-FRU-003", "Papaya", "fruit", "39.00", "0.30"),
    ("JD-FRU-004", "Guava", "fruit", "32.00", "0.30"),
    ("JD-FRU-005", "Pineapple", "fruit", "49.00", "0.34"),
    ("JD-VEG-001", "Morning glory", "vegetables", "20.00", "0.30"),
    ("JD-VEG-002", "Chinese cabbage", "vegetables", "25.00", "0.28"),
    ("JD-VEG-003", "Tomato", "vegetables", "35.00", "0.30"),
    ("JD-VEG-004", "Lime", "vegetables", "22.00", "0.32"),
    ("JD-VEG-005", "Bird's eye chili", "vegetables", "28.00", "0.34"),
    ("JD-RIC-001", "Jasmine rice 5 kg", "rice_and_noodles", "165.00", "0.14"),
    ("JD-RIC-002", "Sticky rice 5 kg", "rice_and_noodles", "150.00", "0.14"),
    ("JD-RIC-003", "Rice noodles", "rice_and_noodles", "25.00", "0.16"),
    ("JD-RIC-004", "Instant noodles 5 pack", "rice_and_noodles", "35.00", "0.18"),
    ("JD-PAN-001", "Fish sauce 700 ml", "pantry", "42.00", "0.26"),
    ("JD-PAN-002", "Soy sauce", "pantry", "38.00", "0.26"),
    ("JD-PAN-003", "Coconut milk", "pantry", "32.00", "0.28"),
    ("JD-PAN-004", "Palm sugar", "pantry", "28.00", "0.24"),
    ("JD-PAN-005", "Vegetable oil 1 L", "pantry", "59.00", "0.16"),
    ("JD-DAI-001", "Eggs 10 pack", "dairy_and_eggs", "55.00", "0.18"),
    ("JD-DAI-002", "Fresh milk 2 L", "dairy_and_eggs", "72.00", "0.20"),
    ("JD-DAI-003", "Yogurt", "dairy_and_eggs", "25.00", "0.30"),
    ("JD-DAI-004", "Condensed milk", "dairy_and_eggs", "27.00", "0.24"),
    ("JD-MEA-001", "Chicken breast", "meat_and_seafood", "89.00", "0.22"),
    ("JD-MEA-002", "Pork belly", "meat_and_seafood", "129.00", "0.20"),
    ("JD-MEA-003", "Minced pork", "meat_and_seafood", "95.00", "0.20"),
    ("JD-MEA-004", "Tilapia", "meat_and_seafood", "79.00", "0.24"),
    ("JD-MEA-005", "Firm tofu", "meat_and_seafood", "22.00", "0.28"),
    ("JD-SNA-001", "Rice crackers", "snacks", "25.00", "0.48"),
    ("JD-SNA-002", "Banana chips", "snacks", "35.00", "0.46"),
    ("JD-SNA-003", "Seaweed snack", "snacks", "20.00", "0.50"),
    ("JD-SNA-004", "Roasted peanuts", "snacks", "30.00", "0.44"),
    ("JD-BEV-001", "Drinking water 6 pack", "beverages", "45.00", "0.34"),
    ("JD-BEV-002", "Green tea", "beverages", "20.00", "0.40"),
    ("JD-BEV-003", "Coconut water", "beverages", "25.00", "0.38"),
    ("JD-BEV-004", "Iced coffee bottle", "beverages", "30.00", "0.42"),
    ("JD-HOU-001", "Dish soap", "household", "35.00", "0.22"),
    ("JD-HOU-002", "Laundry detergent", "household", "89.00", "0.20"),
    ("JD-HOU-003", "Tissue 6 pack", "household", "65.00", "0.24"),
    ("JD-HOU-004", "Trash bags", "household", "40.00", "0.26"),
    ("JD-FRO-001", "Frozen dumplings", "frozen", "79.00", "0.32"),
    ("JD-FRO-002", "Edamame", "frozen", "55.00", "0.34"),
    ("JD-FRO-003", "Coconut ice cream", "frozen", "49.00", "0.36"),
]

# id, name, region, province, opened_on, cancel probability, late probability
STORE_CATALOG = [
    ("STR-001", "JaiDee Sathorn", "Bangkok", "Bangkok", "2019-03-01", 0.035, 0.05),
    ("STR-002", "JaiDee Lat Phrao", "Bangkok", "Bangkok", "2021-06-15", 0.05, 0.10),
    ("STR-003", "JaiDee Ayutthaya", "Central", "Ayutthaya", "2022-02-01", 0.07, 0.15),
    ("STR-004", "JaiDee Chiang Mai", "North", "Chiang Mai", "2022-08-01", 0.06, 0.16),
    ("STR-005", "JaiDee Khon Kaen", "Northeast", "Khon Kaen", "2023-01-10", 0.08, 0.18),
    ("STR-006", "JaiDee Nakhon Ratchasima", "Northeast", "Nakhon Ratchasima", "2023-11-01", 0.09, 0.22),
    ("STR-007", "JaiDee Phuket", "South", "Phuket", "2024-01-15", 0.16, 0.48),
    ("STR-008", "JaiDee Surat Thani", "South", "Surat Thani", "2024-06-01", 0.08, 0.22),
]

GIVEN_NAMES = [
    "Somchai", "Suda", "Anong", "Pranee", "Nattapong", "Kanya", "Arthit", "Malee",
    "Wichai", "Siriporn", "Chakrit", "Pimchanok", "Niran", "Busaba", "Thanakorn",
    "Kannika", "Apinya", "Viroj", "Somsak", "Duangjai", "Krit", "Mali", "Preecha",
    "Siriwan",
]
FAMILY_NAMES = [
    "Srisuk", "Thongchai", "Phanich", "Wongsa", "Saetang", "Chaiyasit", "Boonmee",
    "Rattanakul", "Kaewkla", "Suwannarat", "Intara", "Meechai", "Pongsapak",
    "Jitmongkol", "Dechakul", "Sooksai",
]

LOAD_SQL = {
    "customers": """
        create table raw.customers as
        select
            customer_id,
            full_name,
            email,
            phone,
            region,
            province,
            channel,
            created_at
        from read_csv(?, header=true, all_varchar=true)
    """,
    "orders": """
        create table raw.orders as
        select
            order_id,
            customer_id,
            store_id,
            order_placed_at,
            recorded_at,
            status,
            cast(subtotal_thb as decimal(12, 2)) as subtotal_thb,
            cast(discount_thb as decimal(12, 2)) as discount_thb,
            cast(tax_thb as decimal(12, 2)) as tax_thb,
            cast(delivery_fee_thb as decimal(12, 2)) as delivery_fee_thb,
            cast(order_total_thb as decimal(12, 2)) as order_total_thb
        from read_csv(?, header=true, all_varchar=true)
    """,
    "order_items": """
        create table raw.order_items as
        select
            order_item_id,
            order_id,
            product_id,
            cast(quantity as integer) as quantity,
            cast(unit_price_thb as decimal(12, 2)) as unit_price_thb,
            cast(unit_cost_thb as decimal(12, 2)) as unit_cost_thb,
            cast(line_total_thb as decimal(12, 2)) as line_total_thb
        from read_csv(?, header=true, all_varchar=true)
    """,
    "products": """
        create table raw.products as
        select
            product_id,
            sku,
            product_name,
            category,
            cast(unit_price_thb as decimal(12, 2)) as unit_price_thb,
            cast(unit_cost_thb as decimal(12, 2)) as unit_cost_thb
        from read_csv(?, header=true, all_varchar=true, nullstr='__NONE__')
    """,
    "stores": """
        create table raw.stores as
        select store_id, store_name, region, province, opened_on
        from read_csv(?, header=true, all_varchar=true)
    """,
    "deliveries": """
        create table raw.deliveries as
        select
            delivery_id,
            order_id,
            promised_at,
            nullif(delivered_at, '') as delivered_at,
            status,
            recorded_at
        from read_csv(?, header=true, all_varchar=true)
    """,
    "payments": """
        create table raw.payments as
        select
            payment_id,
            order_id,
            paid_at,
            method,
            status,
            cast(amount_thb as decimal(12, 2)) as amount_thb,
            recorded_at
        from read_csv(?, header=true, all_varchar=true)
    """,
    "reviews": """
        create table raw.reviews as
        select
            review_id,
            order_id,
            customer_id,
            reviewed_at,
            cast(score as integer) as score,
            recorded_at
        from read_csv(?, header=true, all_varchar=true)
    """,
}


def baht(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def is_festival(day: date) -> bool:
    if day.month == 4 and 12 <= day.day <= 15:
        return True
    if day.month == 12 and day.day == 31:
        return True
    if day.month == 1 and day.day in (1, 2):
        return True
    return False


def day_weight(day: date) -> float:
    if day.weekday() >= 5:
        weight = 1.6
    elif day.weekday() == 4:
        weight = 1.15
    else:
        weight = 1.0
    if is_festival(day):
        weight *= 2.4
    return weight


def fmt(moment: datetime) -> str:
    return moment.astimezone(BANGKOK).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def parse_local(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S+07:00").replace(tzinfo=BANGKOK)


def as_utc(value: str) -> str:
    return parse_local(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def window_days() -> list[date]:
    days = []
    day = START_DATE
    while day <= END_DATE:
        days.append(day)
        day += timedelta(days=1)
    return days


def build_stores() -> list[dict]:
    stores = []
    for store_id, name, region, province, opened_on, cancel_p, late_p in STORE_CATALOG:
        stores.append(
            {
                "store_id": store_id,
                "store_name": name,
                "region": region,
                "province": province,
                "opened_on": opened_on,
                "_cancel_p": cancel_p,
                "_late_p": late_p,
            }
        )
    return stores


def build_products() -> list[dict]:
    products = []
    for index, (sku, name, category, price, margin) in enumerate(CATALOG, start=1):
        unit_price = Decimal(price)
        unit_cost = baht(unit_price * (Decimal("1") - Decimal(margin)))
        products.append(
            {
                "product_id": f"PRD-{index:03d}",
                "sku": sku,
                "product_name": name,
                "category": category,
                "unit_price_thb": unit_price,
                "unit_cost_thb": unit_cost,
            }
        )
    return products


def build_customers(rng: random.Random, count: int) -> list[dict]:
    customers = []
    for index in range(1, count + 1):
        region = rng.choices(REGIONS, weights=REGION_WEIGHTS)[0]
        given = rng.choice(GIVEN_NAMES)
        family = rng.choice(FAMILY_NAMES)
        customers.append(
            {
                "customer_id": f"CUST-{index:06d}",
                "full_name": f"{given} {family}",
                "email": f"{given}.{family}.{index}@example.com".lower(),
                "phone": f"08{index:08d}",
                "region": region,
                "province": rng.choice(PROVINCES[region]),
                "channel": rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
                "created_at": "",
                "_keep_shopping": rng.randrange(100) / 100,
            }
        )
    return customers


def pick_status(rng: random.Random, store: dict) -> str:
    if rng.random() < store["_cancel_p"]:
        return "cancelled"
    if rng.random() < 0.05:
        return "returned"
    return rng.choices(
        ["delivered", "shipped", "packed", "placed"],
        weights=[86, 6, 4, 4],
    )[0]


def build_orders(rng: random.Random, customers: list[dict], stores: list[dict], count: int):
    days = window_days()
    weights = [day_weight(day) for day in days]
    chosen_days = rng.choices(days, weights=weights, k=count)
    customer_weights = [
        CHANNEL_ORDER_WEIGHT[customer["channel"]] * (0.25 + customer["_keep_shopping"])
        for customer in customers
    ]
    chosen_customers = rng.choices(customers, weights=customer_weights, k=count)
    by_region: dict[str, list[dict]] = {}
    for store in stores:
        by_region.setdefault(store["region"], []).append(store)

    orders = []
    placed_at = {}
    for index, (day, customer) in enumerate(zip(chosen_days, chosen_customers), start=1):
        hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
        placed = datetime(
            day.year,
            day.month,
            day.day,
            hour,
            rng.randrange(60),
            rng.randrange(60),
            tzinfo=BANGKOK,
        )
        if rng.random() < 0.85:
            store = rng.choice(by_region[customer["region"]])
        else:
            store = rng.choice(stores)
        order_id = f"ORD-{index:06d}"
        orders.append(
            {
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "store_id": store["store_id"],
                "order_placed_at": fmt(placed),
                "recorded_at": fmt(placed + timedelta(minutes=rng.randint(5, 90))),
                "status": pick_status(rng, store),
                "subtotal_thb": Decimal("0.00"),
                "discount_thb": Decimal("0.00"),
                "tax_thb": Decimal("0.00"),
                "delivery_fee_thb": Decimal("0.00"),
                "order_total_thb": Decimal("0.00"),
            }
        )
        placed_at[order_id] = placed
    return orders, placed_at


def delivery_fee(region: str, taxable: Decimal) -> Decimal:
    if region == "Bangkok" and taxable >= Decimal("500"):
        return Decimal("0.00")
    if region == "Bangkok":
        return Decimal("29.00")
    return Decimal("49.00")


def build_items(rng, orders, products, customers_by_id):
    items = []
    item_number = 1
    weights_by_region = {
        region: [
            REGION_CATEGORY_BIAS.get(region, {}).get(product["category"], 1.0)
            for product in products
        ]
        for region in REGIONS
    }
    for order in orders:
        region = customers_by_id[order["customer_id"]]["region"]
        basket = rng.choices([1, 2, 3, 4, 5, 6], weights=[16, 26, 24, 16, 12, 6])[0]
        if customers_by_id[order["customer_id"]]["channel"] == "line" and rng.random() < 0.4:
            basket += 1
        picked = rng.choices(products, weights=weights_by_region[region], k=basket)
        line_totals = []
        for product in picked:
            quantity = rng.choice([1, 1, 1, 2, 2, 3])
            line_total = baht(product["unit_price_thb"] * quantity)
            items.append(
                {
                    "order_item_id": f"ITEM-{item_number:07d}",
                    "order_id": order["order_id"],
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "unit_price_thb": product["unit_price_thb"],
                    "unit_cost_thb": product["unit_cost_thb"],
                    "line_total_thb": line_total,
                }
            )
            line_totals.append(line_total)
            item_number += 1
        subtotal = sum(line_totals, Decimal("0.00"))
        if subtotal >= Decimal("80") and rng.random() < 0.15:
            discount = baht(subtotal * Decimal("0.05"))
        else:
            discount = Decimal("0.00")
        taxable = subtotal - discount
        tax = baht(taxable * VAT_RATE)
        fee = delivery_fee(region, taxable)
        order["subtotal_thb"] = subtotal
        order["discount_thb"] = discount
        order["tax_thb"] = tax
        order["delivery_fee_thb"] = fee
        order["order_total_thb"] = taxable + tax + fee
    return items


def build_deliveries(rng, orders, stores_by_id, customers_by_id, placed_at):
    deliveries = []
    delivered_at = {}
    delay_minutes = {}
    number = 1
    for order in orders:
        if order["status"] == "cancelled":
            continue
        customer = customers_by_id[order["customer_id"]]
        store = stores_by_id[order["store_id"]]
        placed = placed_at[order["order_id"]]
        promised = placed + timedelta(minutes=PROMISE_MINUTES[customer["region"]])
        delivered = None
        if order["status"] in {"placed", "packed"}:
            status = "pending"
        elif order["status"] == "shipped":
            status = "in_transit"
        else:
            status = "delivered"
            delay = int((1 - customer["_keep_shopping"]) * 120) + rng.randint(-10, 15)
            if rng.random() < store["_late_p"]:
                delay += rng.randint(50, 180)
            delivered = promised + timedelta(minutes=delay)
            earliest = placed + timedelta(minutes=15)
            if delivered < earliest:
                delivered = earliest
            delivered_at[order["order_id"]] = delivered
            delay_minutes[order["order_id"]] = int((delivered - promised).total_seconds() // 60)
        event_time = delivered or promised
        deliveries.append(
            {
                "delivery_id": f"DEL-{number:07d}",
                "order_id": order["order_id"],
                "promised_at": fmt(promised),
                "delivered_at": fmt(delivered) if delivered else None,
                "status": status,
                "recorded_at": fmt(event_time + timedelta(minutes=20)),
            }
        )
        number += 1
    return deliveries, delivered_at, delay_minutes


def payment_row(number, order_id, method, status, amount, paid):
    return {
        "payment_id": f"PAY-{number:07d}",
        "order_id": order_id,
        "paid_at": fmt(paid),
        "method": method,
        "status": status,
        "amount_thb": amount,
        "recorded_at": fmt(paid + timedelta(minutes=10)),
    }


def build_payments(rng, orders, placed_at):
    payments = []
    number = 1
    for order in orders:
        total = order["order_total_thb"]
        placed = placed_at[order["order_id"]]
        paid = placed + timedelta(minutes=rng.randint(1, 40))
        method = rng.choices(METHODS, weights=METHOD_WEIGHTS)[0]
        if order["status"] == "cancelled":
            payments.append(payment_row(number, order["order_id"], method, "failed", total, paid))
            number += 1
            continue
        if total >= Decimal("2.00") and rng.random() < 0.12:
            first = baht(total / 2)
            second = total - first
            other = rng.choices(METHODS, weights=METHOD_WEIGHTS)[0]
            payments.append(payment_row(number, order["order_id"], method, "succeeded", first, paid))
            number += 1
            payments.append(
                payment_row(
                    number,
                    order["order_id"],
                    other,
                    "succeeded",
                    second,
                    paid + timedelta(minutes=rng.randint(1, 20)),
                )
            )
            number += 1
        else:
            payments.append(payment_row(number, order["order_id"], method, "succeeded", total, paid))
            number += 1
        if order["status"] == "returned":
            payments.append(
                payment_row(
                    number,
                    order["order_id"],
                    method,
                    "refunded",
                    total,
                    paid + timedelta(days=rng.randint(2, 10)),
                )
            )
            number += 1
    return payments


def score_from_delay(delay: int, rng: random.Random) -> int:
    if delay <= 10:
        base = 5
    elif delay <= 30:
        base = 4
    elif delay <= 75:
        base = 3
    elif delay <= 150:
        base = 2
    else:
        base = 1
    return min(5, max(1, base + rng.choice([-1, 0, 0, 0, 1])))


def build_reviews(rng, orders, delivered_at, delay_minutes):
    reviews = []
    number = 1
    for order in orders:
        delivered = delivered_at.get(order["order_id"])
        if delivered is None or rng.random() > 0.6:
            continue
        reviewed = delivered + timedelta(days=rng.randint(1, 5), hours=rng.randint(8, 20))
        reviews.append(
            {
                "review_id": f"REV-{number:07d}",
                "order_id": order["order_id"],
                "customer_id": order["customer_id"],
                "reviewed_at": fmt(reviewed),
                "score": score_from_delay(delay_minutes[order["order_id"]], rng),
                "recorded_at": fmt(reviewed + timedelta(minutes=15)),
            }
        )
        number += 1
    return reviews


def assign_created_at(rng, customers, orders, placed_at):
    first = {}
    for order in orders:
        placed = placed_at[order["order_id"]]
        current = first.get(order["customer_id"])
        if current is None or placed < current:
            first[order["customer_id"]] = placed
    span = (END_DATE - START_DATE).days
    for customer in customers:
        start = first.get(customer["customer_id"])
        if start is None:
            day = START_DATE + timedelta(days=rng.randrange(span))
            created = datetime(day.year, day.month, day.day, 10, 0, tzinfo=BANGKOK)
        else:
            created = start - timedelta(days=rng.randint(0, 21), hours=rng.randint(0, 10))
        customer["created_at"] = fmt(created)


def zero_cancelled(orders):
    zero = Decimal("0.00")
    for order in orders:
        if order["status"] == "cancelled":
            order["subtotal_thb"] = zero
            order["discount_thb"] = zero
            order["tax_thb"] = zero
            order["delivery_fee_thb"] = zero
            order["order_total_thb"] = zero


def apply_issues(rng, tables):
    orders = tables["orders"]
    customers = tables["customers"]
    products = tables["products"]
    items = tables["order_items"]
    payments = tables["payments"]
    deliveries = tables["deliveries"]
    reviews = tables["reviews"]

    for product in products[:4]:
        product["category"] = None
    for product in products[4:8]:
        product["category"] = ""

    for item in rng.sample(items, 15):
        item["quantity"] = -abs(int(item["quantity"]))
        item["line_total_thb"] = -abs(item["line_total_thb"])

    sample_product = products[10]
    for offset in range(10):
        price = sample_product["unit_price_thb"]
        items.append(
            {
                "order_item_id": f"ITEM-{len(items) + 1:07d}",
                "order_id": f"ORD-{900000 + offset:06d}",
                "product_id": sample_product["product_id"],
                "quantity": 1,
                "unit_price_thb": price,
                "unit_cost_thb": sample_product["unit_cost_thb"],
                "line_total_thb": price,
            }
        )
    for offset in range(8):
        paid = datetime(2026, 5, 1, 12, offset, tzinfo=BANGKOK)
        payments.append(
            payment_row(
                len(payments) + 1,
                f"ORD-{910000 + offset:06d}",
                "promptpay",
                "succeeded",
                Decimal("100.00"),
                paid,
            )
        )
    for offset in range(6):
        reviewed = datetime(2026, 6, 1, 9, offset, tzinfo=BANGKOK)
        reviews.append(
            {
                "review_id": f"REV-{len(reviews) + 1:07d}",
                "order_id": f"ORD-{920000 + offset:06d}",
                "customer_id": customers[offset]["customer_id"],
                "reviewed_at": fmt(reviewed),
                "score": 5,
                "recorded_at": fmt(reviewed + timedelta(minutes=15)),
            }
        )

    eligible = [order for order in orders if order["status"] != "cancelled"]
    overpaid = rng.sample(eligible, 20)
    overpaid_ids = {order["order_id"] for order in overpaid}
    rest = [order for order in eligible if order["order_id"] not in overpaid_ids]
    failed_with_success = rng.sample(rest, 20)
    for order in overpaid:
        paid = parse_local(order["order_placed_at"]) + timedelta(minutes=50)
        payments.append(
            payment_row(
                len(payments) + 1,
                order["order_id"],
                "promptpay",
                "succeeded",
                Decimal("25.00"),
                paid,
            )
        )
    for order in failed_with_success:
        paid = parse_local(order["order_placed_at"]) + timedelta(minutes=5)
        payments.append(
            payment_row(
                len(payments) + 1,
                order["order_id"],
                "credit_card",
                "failed",
                order["order_total_thb"],
                paid,
            )
        )

    delivered_orders = [order for order in orders if order["status"] == "delivered"]
    rewritten = rng.sample(delivered_orders, 75)
    for order in rewritten[:30]:
        order["status"] = "Delivered"
    for order in rewritten[30:55]:
        order["status"] = "complete"
    for order in rewritten[55:]:
        order["status"] = "สำเร็จ"

    for order in rng.sample(orders, 40):
        placed = parse_local(order["order_placed_at"])
        order["recorded_at"] = fmt(placed + timedelta(days=rng.randint(6, 12), hours=rng.randint(0, 8)))

    converted = set()
    for target in (date(2025, 10, 1), date(2026, 4, 1), date(2026, 9, 1), date(2026, 10, 1)):
        pool = []
        for order in orders:
            if order["order_id"] in converted:
                continue
            if parse_local(order["order_placed_at"]).date() == target:
                pool.append(order)
        if not pool:
            continue
        for order in rng.sample(pool, min(4, len(pool))):
            placed = parse_local(order["order_placed_at"]).replace(
                hour=rng.randint(0, 5),
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
            )
            order["order_placed_at"] = as_utc(fmt(placed))
            converted.add(order["order_id"])

    utc_pool = [order for order in orders if order["order_id"] not in converted]
    for order in rng.sample(utc_pool, 60):
        order["order_placed_at"] = as_utc(order["order_placed_at"])
        converted.add(order["order_id"])
    naive_pool = [order for order in orders if order["order_id"] not in converted]
    for order in rng.sample(naive_pool, 50):
        order["order_placed_at"] = order["order_placed_at"].removesuffix("+07:00")

    stamped = [row for row in deliveries if row["delivered_at"]]
    for row in rng.sample(stamped, 25):
        row["delivered_at"] = row["delivered_at"].removesuffix("+07:00")
    for row in rng.sample(payments, 25):
        if row["paid_at"].endswith("+07:00"):
            row["paid_at"] = as_utc(row["paid_at"])

    next_customer = len(customers) + 1
    for customer in rng.sample(customers, 12):
        twin = dict(customer)
        twin["customer_id"] = f"CUST-{next_customer:06d}"
        next_customer += 1
        twin["created_at"] = fmt(parse_local(customer["created_at"]) + timedelta(days=12))
        customers.append(twin)

    for order in rng.sample(orders, 15):
        orders.append(dict(order))


def strip_internal(rows):
    for row in rows:
        for key in [key for key in row if key.startswith("_")]:
            del row[key]


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_value(row[column]) for column in columns})


def write_duckdb(db_path: Path, raw_dir: Path, tables: dict) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    Path(str(db_path) + ".wal").unlink(missing_ok=True)
    connection = duckdb.connect(str(db_path))
    try:
        connection.execute("create schema raw")
        for name in TABLE_NAMES:
            connection.execute(LOAD_SQL[name], [str(raw_dir / f"{name}.csv")])
        null_ids = [row["product_id"] for row in tables["products"] if row["category"] is None]
        if null_ids:
            marks = ", ".join("?" for _ in null_ids)
            connection.execute(
                f"update raw.products set category = null where product_id in ({marks})",
                null_ids,
            )
    finally:
        connection.close()


def write_outputs(output_dir: Path, tables: dict) -> None:
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in TABLE_NAMES:
        write_csv(raw_dir / f"{name}.csv", tables[name], COLUMNS[name])
    write_duckdb(output_dir / "jaidee.duckdb", raw_dir, tables)


def generate(
    *,
    seed: int = 42,
    scale: str = "teaching",
    clean: bool = False,
    output_dir: Path | str = "data",
    write_files: bool = True,
) -> dict[str, list[dict]]:
    if scale not in SCALES:
        known = ", ".join(SCALES)
        raise ValueError(f"Unknown scale {scale!r}. Choose from: {known}")
    spec = SCALES[scale]
    rng = random.Random(seed)
    stores = build_stores()
    products = build_products()
    customers = build_customers(rng, spec["customers"])
    orders, placed_at = build_orders(rng, customers, stores, spec["orders"])
    customers_by_id = {row["customer_id"]: row for row in customers}
    stores_by_id = {row["store_id"]: row for row in stores}
    items = build_items(rng, orders, products, customers_by_id)
    deliveries, delivered_at, delay_minutes = build_deliveries(
        rng, orders, stores_by_id, customers_by_id, placed_at
    )
    payments = build_payments(rng, orders, placed_at)
    reviews = build_reviews(rng, orders, delivered_at, delay_minutes)
    assign_created_at(rng, customers, orders, placed_at)

    tables = {
        "customers": customers,
        "orders": orders,
        "order_items": items,
        "products": products,
        "stores": stores,
        "deliveries": deliveries,
        "payments": payments,
        "reviews": reviews,
    }
    if clean:
        zero_cancelled(orders)
    else:
        apply_issues(rng, tables)
    for rows in tables.values():
        strip_internal(rows)
    if write_files:
        write_outputs(Path(output_dir), tables)
    return tables


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate JaiDee Mart raw tables.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", choices=tuple(SCALES), default="teaching")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    tables = generate(
        seed=args.seed,
        scale=args.scale,
        clean=args.clean,
        output_dir=args.output,
    )
    print(f"seed={args.seed} scale={args.scale} clean={args.clean}")
    for name in TABLE_NAMES:
        print(f"{name}: {len(tables[name])}")
    print(f"wrote {(args.output / 'raw').as_posix()}")
    print(f"wrote {(args.output / 'jaidee.duckdb').as_posix()}")


if __name__ == "__main__":
    main()
