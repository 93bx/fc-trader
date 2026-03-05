"""Unit tests for bot.utils: bid increments, profit, parse_coin_value, random_delay."""

import sys
from pathlib import Path

import pytest

# Ensure bot package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.utils import (
    EA_BID_INCREMENTS,
    calculate_max_buy,
    calculate_profit,
    get_next_bid,
    get_prev_bid,
    parse_coin_value,
    random_delay,
)


class TestGetNextBid:
    """Tests for get_next_bid at and around bracket boundaries."""

    def test_minimum_returns_200(self) -> None:
        assert get_next_bid(0) == 200
        assert get_next_bid(100) == 200
        assert get_next_bid(199) == 200

    def test_first_bracket(self) -> None:
        assert get_next_bid(200) == 250
        assert get_next_bid(250) == 300
        assert get_next_bid(999) == 1000

    def test_second_bracket(self) -> None:
        assert get_next_bid(1000) == 1100
        assert get_next_bid(1100) == 1200
        assert get_next_bid(9999) == 10000

    def test_third_bracket(self) -> None:
        assert get_next_bid(10000) == 10250
        assert get_next_bid(14999) == 15000

    def test_fourth_bracket(self) -> None:
        assert get_next_bid(50000) == 50500
        assert get_next_bid(99999) == 100000

    def test_top_bracket(self) -> None:
        assert get_next_bid(100000) == 101000
        assert get_next_bid(101000) == 102000


class TestGetPrevBid:
    """Tests for get_prev_bid."""

    def test_below_floor_returns_200(self) -> None:
        assert get_prev_bid(199) == 200
        assert get_prev_bid(50) == 200

    def test_exact_boundaries(self) -> None:
        assert get_prev_bid(200) == 200
        assert get_prev_bid(1000) == 1000
        assert get_prev_bid(1050) == 1000  # 1050 not valid; nearest below is 1000
        assert get_prev_bid(1100) == 1100
        assert get_prev_bid(1049) == 1000

    def test_mid_brackets(self) -> None:
        assert get_prev_bid(1234) == 1200
        assert get_prev_bid(100000) == 100000
        assert get_prev_bid(150000) == 150000


class TestCalculateProfit:
    """Tests for calculate_profit (EA 5% tax)."""

    def test_zero_profit(self) -> None:
        # sell * 0.95 = buy -> profit 0
        buy = 9500
        sell = 10000
        r = calculate_profit(buy, sell)
        assert r.net_received == 9500
        assert r.profit == 0
        assert r.roi_pct == 0.0

    def test_positive_profit(self) -> None:
        buy = 10000
        sell = 12000
        r = calculate_profit(buy, sell)
        assert r.net_received == 11400
        assert r.profit == 1400
        assert abs(r.roi_pct - 14.0) < 0.01

    def test_negative_profit(self) -> None:
        buy = 10000
        sell = 9000
        r = calculate_profit(buy, sell)
        assert r.net_received == 8550
        assert r.profit == -1450
        assert r.roi_pct < 0


class TestCalculateMaxBuy:
    """Tests for calculate_max_buy (round down to valid bid)."""

    def test_basic(self) -> None:
        # target_sell 10000, min_profit_pct 10 -> (10000*0.95)*0.9 = 8550
        r = calculate_max_buy(10000, 10.0)
        assert r <= 8550
        assert r >= 8300
        # Must be valid bid (multiple of step in its bracket)
        assert get_prev_bid(r) == r

    def test_rounds_down(self) -> None:
        r = calculate_max_buy(5000, 5.0)
        assert get_prev_bid(int(5000 * 0.95 * 0.95) + 1) >= r


class TestParseCoinValue:
    """Tests for parse_coin_value."""

    def test_plain_number(self) -> None:
        assert parse_coin_value("200") == 200
        assert parse_coin_value("14500") == 14500

    def test_with_comma(self) -> None:
        assert parse_coin_value("14,500") == 14500
        assert parse_coin_value("1,000,000") == 1000000

    def test_k_suffix(self) -> None:
        assert parse_coin_value("14.5K") == 14500
        assert parse_coin_value("1K") == 1000
        assert parse_coin_value("100k") == 100000

    def test_m_suffix(self) -> None:
        assert parse_coin_value("1.2M") == 1200000
        assert parse_coin_value("1m") == 1000000

    def test_invalid_returns_none(self) -> None:
        assert parse_coin_value("") is None
        assert parse_coin_value("abc") is None
        assert parse_coin_value("12.34.56") is None

    def test_strip_and_lower(self) -> None:
        assert parse_coin_value("  14.5K  ") == 14500
        assert parse_coin_value("1.2m") == 1200000


class TestRandomDelay:
    """Tests for random_delay (mock time.sleep)."""

    def test_calls_sleep_in_range(self) -> None:
        from unittest.mock import patch

        with patch("bot.utils.time.sleep") as mock_sleep:
            with patch("bot.utils.random.uniform", return_value=1.5):
                random_delay(1.0, 2.0)
        mock_sleep.assert_called_once_with(1.5)

    def test_uniform_receives_min_max(self) -> None:
        from unittest.mock import patch

        with patch("bot.utils.time.sleep"):
            with patch("bot.utils.random.uniform") as mock_uniform:
                mock_uniform.return_value = 0.5
                random_delay(0.2, 0.8)
        mock_uniform.assert_called_once_with(0.2, 0.8)
