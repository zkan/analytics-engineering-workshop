import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import duckdb
import pytest

from generator.generate import (
    END_DATE,
    SCALES,
    START_DATE,
    TABLE_NAMES,
    day_weight,
    generate,
    is_festival,
)

BANGKOK = ZoneInfo("Asia/Bangkok")


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if len(value) == 19:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=BANGKOK)
    return datetime.fromisoformat(value)


def each_day():
    day = START_DATE
    while day <= END_DATE:
        yield day
        day += timedelta(days=1)


def payments_for(tables):
    grouped = defaultdict(list)
    for payment in tables["payments"]:
        grouped[payment["order_id"]].append(payment)
    return grouped


def items_for(tables):
    grouped = defaultdict(list)
    for item in tables["order_items"]:
        grouped[item["order_id"]].append(item)
    return grouped


@pytest.fixture(scope="module")
def clean():
    return generate(seed=42, scale="teaching", clean=True, write_files=False)


@pytest.fixture(scope="module")
def trap():
    return generate(seed=42, scale="teaching", clean=False, write_files=False)


def test_day_weight_raises_weekends_and_festivals():
    tuesday = next(day for day in each_day() if day.weekday() == 1 and not is_festival(day))
    saturday = next(day for day in each_day() if day.weekday() == 5 and not is_festival(day))
    assert day_weight(saturday) > day_weight(tuesday)
    assert day_weight(date(2026, 4, 13)) > day_weight(tuesday)
    assert day_weight(date(2026, 1, 1)) > day_weight(tuesday)
    assert is_festival(date(2025, 12, 31))
    assert not is_festival(tuesday)


def test_same_seed_writes_identical_csv(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(seed=42, scale="teaching", clean=True, output_dir=first)
    generate(seed=42, scale="teaching", clean=True, output_dir=second)
    for name in TABLE_NAMES:
        assert (first / "raw" / f"{name}.csv").read_bytes() == (
            second / "raw" / f"{name}.csv"
        ).read_bytes()


def test_different_seed_changes_orders():
    first = generate(seed=1, scale="teaching", clean=True, write_files=False)
    second = generate(seed=2, scale="teaching", clean=True, write_files=False)
    assert [row["customer_id"] for row in first["orders"]] != [
        row["customer_id"] for row in second["orders"]
    ]


def test_large_scale_has_more_rows_than_teaching():
    teaching = generate(seed=42, scale="teaching", clean=True, write_files=False)
    large = generate(seed=42, scale="large", clean=True, write_files=False)
    assert len(teaching["orders"]) == SCALES["teaching"]["orders"]
    assert len(large["orders"]) == SCALES["large"]["orders"]
    assert len(teaching["customers"]) == SCALES["teaching"]["customers"]
    assert len(large["customers"]) == SCALES["large"]["customers"]
    assert len(large["orders"]) == len(teaching["orders"]) * 10
    assert len(large["customers"]) == len(teaching["customers"]) * 10
    assert len(large["order_items"]) > len(teaching["order_items"]) * 5
    assert len(large["payments"]) > len(teaching["payments"])
    assert len(large["products"]) == len(teaching["products"])
    assert len(large["stores"]) == len(teaching["stores"])


def test_clean_referential_integrity(clean):
    customer_ids = {row["customer_id"] for row in clean["customers"]}
    order_ids = {row["order_id"] for row in clean["orders"]}
    product_ids = {row["product_id"] for row in clean["products"]}
    store_ids = {row["store_id"] for row in clean["stores"]}
    assert len(customer_ids) == len(clean["customers"])
    assert len(order_ids) == len(clean["orders"])
    assert len(product_ids) == len(clean["products"])
    assert len(store_ids) == len(clean["stores"])
    assert len({row["order_item_id"] for row in clean["order_items"]}) == len(clean["order_items"])
    assert len({row["payment_id"] for row in clean["payments"]}) == len(clean["payments"])
    assert len({row["delivery_id"] for row in clean["deliveries"]}) == len(clean["deliveries"])
    assert len({row["review_id"] for row in clean["reviews"]}) == len(clean["reviews"])
    assert len({row["email"] for row in clean["customers"]}) == len(clean["customers"])
    assert len({row["phone"] for row in clean["customers"]}) == len(clean["customers"])

    for order in clean["orders"]:
        assert order["customer_id"] in customer_ids
        assert order["store_id"] in store_ids
    for item in clean["order_items"]:
        assert item["order_id"] in order_ids
        assert item["product_id"] in product_ids
        assert item["quantity"] > 0
    for delivery in clean["deliveries"]:
        assert delivery["order_id"] in order_ids
    for payment in clean["payments"]:
        assert payment["order_id"] in order_ids
    for review in clean["reviews"]:
        assert review["order_id"] in order_ids
        assert review["customer_id"] in customer_ids
    for product in clean["products"]:
        assert product["category"]
        assert product["unit_cost_thb"] < product["unit_price_thb"]


def test_clean_money_and_timestamps(clean):
    by_order = items_for(clean)
    payers = payments_for(clean)
    customers = {row["customer_id"]: row for row in clean["customers"]}
    allowed = {"placed", "packed", "shipped", "delivered", "cancelled", "returned"}
    timestamp_columns = {
        "customers": ["created_at"],
        "orders": ["order_placed_at", "recorded_at"],
        "deliveries": ["promised_at", "delivered_at", "recorded_at"],
        "payments": ["paid_at", "recorded_at"],
        "reviews": ["reviewed_at", "recorded_at"],
    }
    for table, columns in timestamp_columns.items():
        for row in clean[table]:
            for column in columns:
                if row[column]:
                    assert row[column].endswith("+07:00")

    assert {row["status"] for row in clean["orders"]} <= allowed
    saw_split = False
    saw_refund = False
    saw_cancelled = False
    for order in clean["orders"]:
        lines = by_order[order["order_id"]]
        pays = payers[order["order_id"]]
        succeeded = sum(
            (pay["amount_thb"] for pay in pays if pay["status"] == "succeeded"),
            Decimal("0.00"),
        )
        assert succeeded == order["order_total_thb"]
        assert not any(pay["status"] == "failed" and succeeded > 0 for pay in pays)
        if order["status"] == "cancelled":
            saw_cancelled = True
            assert order["order_total_thb"] == Decimal("0.00")
            assert order["subtotal_thb"] == Decimal("0.00")
            assert any(pay["status"] == "failed" and pay["amount_thb"] > 0 for pay in pays)
            assert lines
            continue
        subtotal = sum((line["line_total_thb"] for line in lines), Decimal("0.00"))
        assert order["subtotal_thb"] == subtotal
        for line in lines:
            assert line["line_total_thb"] == money(line["unit_price_thb"] * line["quantity"])
        taxable = subtotal - order["discount_thb"]
        region = customers[order["customer_id"]]["region"]
        if region == "Bangkok" and taxable >= Decimal("500"):
            fee = Decimal("0.00")
        elif region == "Bangkok":
            fee = Decimal("29.00")
        else:
            fee = Decimal("49.00")
        assert order["delivery_fee_thb"] == fee
        assert order["tax_thb"] == money(taxable * Decimal("0.07"))
        assert order["order_total_thb"] == taxable + order["tax_thb"] + fee
        placed = parse_ts(order["order_placed_at"])
        recorded = parse_ts(order["recorded_at"])
        assert timedelta(0) <= recorded - placed <= timedelta(hours=2)
        if sum(pay["status"] == "succeeded" for pay in pays) >= 2:
            saw_split = True
        if order["status"] == "returned":
            refunded = sum(
                (pay["amount_thb"] for pay in pays if pay["status"] == "refunded"),
                Decimal("0.00"),
            )
            assert refunded == order["order_total_thb"]
            saw_refund = True
    assert saw_cancelled and saw_split and saw_refund


def test_clean_patterns_support_the_workshop_questions(clean):
    counts = defaultdict(int)
    for order in clean["orders"]:
        counts[parse_ts(order["order_placed_at"]).date()] += 1
    weekend = []
    weekday = []
    festival = []
    for day in each_day():
        if is_festival(day):
            festival.append(counts[day])
        elif day.weekday() >= 5:
            weekend.append(counts[day])
        elif day.weekday() < 4:
            weekday.append(counts[day])
    assert sum(weekend) / len(weekend) > sum(weekday) / len(weekday) * 1.15
    assert sum(festival) / len(festival) > sum(weekday) / len(weekday) * 1.5

    orders_per_customer = defaultdict(int)
    for order in clean["orders"]:
        orders_per_customer[order["customer_id"]] += 1
    line = [
        orders_per_customer[row["customer_id"]]
        for row in clean["customers"]
        if row["channel"] == "line"
    ]
    walk_in = [
        orders_per_customer[row["customer_id"]]
        for row in clean["customers"]
        if row["channel"] == "walk_in"
    ]
    assert sum(line) / len(line) > sum(walk_in) / len(walk_in) * 1.8

    deliveries = {row["order_id"]: row for row in clean["deliveries"]}
    def late_share(store_id):
        matched = [
            deliveries[order["order_id"]]
            for order in clean["orders"]
            if order["store_id"] == store_id
            and order["status"] == "delivered"
            and order["order_id"] in deliveries
            and deliveries[order["order_id"]]["status"] == "delivered"
        ]
        late = 0
        for delivery in matched:
            if parse_ts(delivery["delivered_at"]) > parse_ts(delivery["promised_at"]):
                late += 1
        return late / len(matched)

    assert late_share("STR-007") > late_share("STR-001")

    review_by_order = {row["order_id"]: row for row in clean["reviews"]}
    on_time = []
    late_scores = []
    customer_delay = defaultdict(list)
    for delivery in clean["deliveries"]:
        if delivery["status"] != "delivered":
            continue
        delay = parse_ts(delivery["delivered_at"]) - parse_ts(delivery["promised_at"])
        customer_id = next(
            order["customer_id"]
            for order in clean["orders"]
            if order["order_id"] == delivery["order_id"]
        )
        customer_delay[customer_id].append(delay.total_seconds())
        review = review_by_order.get(delivery["order_id"])
        if review is None:
            continue
        if delay <= timedelta(minutes=30):
            on_time.append(review["score"])
        else:
            late_scores.append(review["score"])
    assert sum(on_time) / len(on_time) > sum(late_scores) / len(late_scores) + 0.4

    high = []
    low = []
    for customer_id, delays in customer_delay.items():
        average = sum(delays) / len(delays)
        bucket = high if average > 45 * 60 else low
        bucket.append(orders_per_customer[customer_id])
    assert high and low
    assert sum(high) / len(high) < sum(low) / len(low)

    snacks = []
    rice = []
    for product in clean["products"]:
        margin = (product["unit_price_thb"] - product["unit_cost_thb"]) / product["unit_price_thb"]
        if product["category"] == "snacks":
            snacks.append(margin)
        elif product["category"] == "rice_and_noodles":
            rice.append(margin)
    assert sum(snacks) / len(snacks) > sum(rice) / len(rice)

    methods = {row["method"] for row in clean["payments"]}
    assert {
        "promptpay",
        "cash_on_delivery",
        "credit_card",
        "truemoney",
        "bank_transfer",
    } <= methods
    assert {row["region"] for row in clean["customers"]} == {
        "Bangkok",
        "Central",
        "North",
        "Northeast",
        "South",
    }


def test_trap_duplicate_order_ids(clean, trap):
    clean_ids = [row["order_id"] for row in clean["orders"]]
    trap_ids = [row["order_id"] for row in trap["orders"]]
    assert len(clean_ids) == len(set(clean_ids))
    assert len(trap_ids) > len(set(trap_ids))
    assert set(trap_ids) == set(clean_ids)


def test_trap_split_customer_identities(clean, trap):
    def shared(rows, column):
        seen = defaultdict(set)
        for row in rows:
            seen[row[column]].add(row["customer_id"])
        return any(len(ids) > 1 for ids in seen.values())

    assert not shared(clean["customers"], "email")
    assert not shared(clean["customers"], "phone")
    assert shared(trap["customers"], "email")
    assert shared(trap["customers"], "phone")
    assert len(trap["customers"]) > len(clean["customers"])


def test_trap_late_arriving_orders(trap):
    late = 0
    for order in trap["orders"]:
        gap = parse_ts(order["recorded_at"]) - parse_ts(order["order_placed_at"])
        if gap >= timedelta(days=5):
            late += 1
    assert late >= 20


def test_trap_inconsistent_status_values(trap):
    statuses = {row["status"] for row in trap["orders"]}
    assert "Delivered" in statuses
    assert "complete" in statuses
    assert "สำเร็จ" in statuses
    assert "delivered" in statuses


def test_trap_mixed_timestamps(trap):
    placed = [row["order_placed_at"] for row in trap["orders"]]
    assert any(value.endswith("+07:00") for value in placed)
    assert any(value.endswith("Z") for value in placed)
    assert any(len(value) == 19 for value in placed)
    crossed = False
    for value in placed:
        if not value.endswith("Z"):
            continue
        utc = parse_ts(value)
        if utc.date() != utc.astimezone(BANGKOK).date():
            crossed = True
            break
    assert crossed
    assert any(row["delivered_at"] and len(row["delivered_at"]) == 19 for row in trap["deliveries"])
    assert any(row["paid_at"].endswith("Z") for row in trap["payments"])


def test_trap_orphan_children(trap):
    order_ids = {row["order_id"] for row in trap["orders"]}
    product_ids = {row["product_id"] for row in trap["products"]}
    orphan_items = [row for row in trap["order_items"] if row["order_id"] not in order_ids]
    orphan_payments = [row for row in trap["payments"] if row["order_id"] not in order_ids]
    orphan_reviews = [row for row in trap["reviews"] if row["order_id"] not in order_ids]
    assert orphan_items and orphan_payments and orphan_reviews
    assert all(row["product_id"] in product_ids for row in orphan_items)


def test_trap_cancelled_orders_keep_positive_totals(clean, trap):
    assert any(row["status"] == "cancelled" for row in clean["orders"])
    assert all(
        row["order_total_thb"] == Decimal("0.00")
        for row in clean["orders"]
        if row["status"] == "cancelled"
    )
    assert any(
        row["status"] == "cancelled" and row["order_total_thb"] > 0 for row in trap["orders"]
    )


def test_trap_payments_exceed_order_or_include_failed(clean, trap):
    def problems(tables):
        headers = {}
        for order in tables["orders"]:
            headers.setdefault(order["order_id"], order)
        over = False
        failed_included = False
        for order_id, pays in payments_for(tables).items():
            order = headers.get(order_id)
            if order is None:
                continue
            succeeded = sum(
                (pay["amount_thb"] for pay in pays if pay["status"] == "succeeded"),
                Decimal("0.00"),
            )
            if succeeded > order["order_total_thb"]:
                over = True
            if succeeded > 0 and any(
                pay["status"] == "failed" and pay["amount_thb"] > 0 for pay in pays
            ):
                failed_included = True
        return over, failed_included

    assert problems(clean) == (False, False)
    over, failed_included = problems(trap)
    assert over and failed_included


def test_trap_bad_categories_and_quantities(clean, trap):
    assert all(row["category"] for row in clean["products"])
    assert all(row["quantity"] > 0 for row in clean["order_items"])
    assert any(row["category"] is None for row in trap["products"])
    assert any(row["category"] == "" for row in trap["products"])
    assert any(row["quantity"] < 0 for row in trap["order_items"])


def test_clean_duckdb_load_matches_tables(tmp_path):
    tables = generate(seed=42, scale="teaching", clean=True, output_dir=tmp_path)
    connection = duckdb.connect(str(tmp_path / "jaidee.duckdb"), read_only=True)
    try:
        for name in TABLE_NAMES:
            count = connection.execute(f"select count(*) from raw.{name}").fetchone()[0]
            assert count == len(tables[name])
        kind = connection.execute(
            "select typeof(order_total_thb) from raw.orders limit 1"
        ).fetchone()[0]
        assert kind.upper().startswith("DECIMAL")
        empty_categories = connection.execute(
            "select count(*) from raw.products where category is null or category = ''"
        ).fetchone()[0]
        assert empty_categories == 0
    finally:
        connection.close()


def test_trap_null_and_blank_categories_in_duckdb(tmp_path):
    generate(seed=42, scale="teaching", clean=False, output_dir=tmp_path)
    connection = duckdb.connect(str(tmp_path / "jaidee.duckdb"), read_only=True)
    try:
        nulls = connection.execute(
            "select count(*) from raw.products where category is null"
        ).fetchone()[0]
        blanks = connection.execute(
            "select count(*) from raw.products where category = ''"
        ).fetchone()[0]
        assert nulls >= 1
        assert blanks >= 1
    finally:
        connection.close()


def test_cli_writes_clean_extract(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "generator.generate",
            "--seed",
            "42",
            "--scale",
            "teaching",
            "--clean",
            "--output",
            str(tmp_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "orders: 12000" in completed.stdout
    assert (tmp_path / "jaidee.duckdb").exists()
    assert (tmp_path / "raw" / "orders.csv").exists()
