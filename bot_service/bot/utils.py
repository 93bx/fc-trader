"""EA bid increments, profit math, coin parsing, and random delay. No UI or DB logic."""

import random
import time
from typing import List, Optional, Tuple

from bot.models import ProfitResult

# EA bid brackets: (low_inclusive, high_inclusive_or_None, step)
EA_BID_INCREMENTS: List[Tuple[int, Optional[int], int]] = [
    (200, 1_000, 50),
    (1_000, 10_000, 100),
    (10_000, 50_000, 250),
    (50_000, 100_000, 500),
    (100_000, None, 1_000),
]


def get_next_bid(current_price: int) -> int:
    """Return the next valid bid above current_price using EA's increment table."""
    if current_price < 200:
        return 200
    for low, high, step in EA_BID_INCREMENTS:
        if high is not None and current_price >= high:
            continue
        if current_price < low:
            return low
        # current_price is in [low, high] (or >= low if high is None)
        n = (current_price - low) // step
        next_in_bracket = low + (n + 1) * step
        if high is None:
            return next_in_bracket
        if next_in_bracket <= high:
            return next_in_bracket
        # overflow to next bracket
        # (only reachable for 50k-100k boundary → 100000+500 handled by top bracket)
        return high + step if high == 100_000 else low + step
    return current_price + 1_000


def get_prev_bid(current_price: int) -> int:
    """Return the nearest valid bid at or below current_price. Below EA floor returns 200."""
    if current_price < 200:
        return 200
    for low, high, step in EA_BID_INCREMENTS:
        if high is not None and current_price > high:
            continue
        if current_price < low:
            continue
        # current_price in [low, high] or >= low
        n = (current_price - low) // step
        return low + n * step
    # above top bracket
    low, _, step = EA_BID_INCREMENTS[-1]
    n = (current_price - low) // step
    return low + n * step


def calculate_profit(buy_price: int, sell_price: int) -> ProfitResult:
    """Calculate net profit after EA 5% tax."""
    net_received = int(sell_price * 0.95)
    profit = net_received - buy_price
    roi_pct = (profit / buy_price) * 100.0 if buy_price else 0.0
    return ProfitResult(net_received=net_received, profit=profit, roi_pct=roi_pct)


def calculate_max_buy(target_sell: int, min_profit_pct: float) -> int:
    """Work backwards from desired sell price to maximum buy price.

    max_buy = (target_sell * 0.95) * (1 - min_profit_pct/100), then round down
    to nearest valid bid increment.
    """
    if min_profit_pct >= 100 or target_sell <= 0:
        return 200
    raw = (target_sell * 0.95) * (1 - min_profit_pct / 100.0)
    max_buy_float = max(200.0, raw)
    return get_prev_bid(int(max_buy_float))


def parse_coin_value(text: str) -> Optional[int]:
    """Parse FC coin display strings to integer.

    Handles: "14,500" -> 14500, "14.5K" -> 14500, "1.2M" -> 1200000.
    Returns None if parsing fails.
    """
    if not text or not isinstance(text, str):
        return None
    s = text.strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    s_lower = s.lower()
    if s_lower.endswith("m"):
        try:
            return int(float(s_lower[:-1]) * 1_000_000)
        except ValueError:
            return None
    if s_lower.endswith("k"):
        try:
            return int(float(s_lower[:-1]) * 1_000)
        except ValueError:
            return None
    try:
        return int(float(s))
    except ValueError:
        return None


def random_delay(min_s: float, max_s: float) -> None:
    """Sleep for a random duration between min_s and max_s."""
    time.sleep(random.uniform(min_s, max_s))
