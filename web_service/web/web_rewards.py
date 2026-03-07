"""FC 26 WEB APP — Auto-claim rewards (Rivals, Squad Battles, Champions, Objectives)."""

from __future__ import annotations

import asyncio

from loguru import logger

from web.anti_detect.timing import KSATiming
from web.config_loader import WebConfig
from web.web_navigator import WebNavigator


class WebRewards:
    """Navigates to reward sections and claims all available milestone rewards."""

    def __init__(self, navigator: WebNavigator, timing: KSATiming, cfg: WebConfig) -> None:
        """Store navigator, timing and rewards configuration."""
        self._nav = navigator
        self._timing = timing
        self._cfg = cfg

    async def claim_all(self) -> dict:
        """Claim all configured reward types; returns per-type counts."""
        results: dict = {"rivals": 0, "squad_battles": 0, "champions": 0, "objectives": 0}
        if not self._cfg.rewards.auto_claim:
            return results
        if self._cfg.rewards.claim_rivals:
            results["rivals"] = await self.claim_rivals()
        if self._cfg.rewards.claim_squad_battles:
            results["squad_battles"] = await self.claim_squad_battles()
        if self._cfg.rewards.claim_champions:
            results["champions"] = await self.claim_champions()
        results["objectives"] = await self.claim_objectives()
        logger.info("Rewards claimed: {}", results)
        return results

    async def claim_rivals(self) -> int:
        """Navigate to Division Rivals and claim available milestone rewards."""
        return await self._claim_section(
            nav_selector="a:has-text('Division Rivals'), a:has-text('Rivals')",
            claim_selector="button:has-text('Claim'), button:has-text('Collect')",
            label="Rivals",
        )

    async def claim_squad_battles(self) -> int:
        """Navigate to Squad Battles and claim reward."""
        return await self._claim_section(
            nav_selector="a:has-text('Squad Battles')",
            claim_selector="button:has-text('Claim'), button:has-text('Collect')",
            label="Squad Battles",
        )

    async def claim_champions(self) -> int:
        """Navigate to UT Champions and claim rewards."""
        return await self._claim_section(
            nav_selector="a:has-text('Champions'), a:has-text('FUT Champions')",
            claim_selector="button:has-text('Claim'), button:has-text('Collect')",
            label="Champions",
        )

    async def claim_objectives(self) -> int:
        """Navigate to Objectives and complete/claim available entries."""
        await self._nav.go_to_objectives()
        await asyncio.sleep(self._timing.human_delay())
        page = self._nav._browser.page
        if page is None:
            return 0
        count = 0
        try:
            btns = await page.locator(
                "button:has-text('Claim'), button:has-text('Collect'), button:has-text('Complete')"
            ).all()
            for btn in btns:
                try:
                    if await btn.is_enabled(timeout=1_000):
                        await btn.click()
                        await asyncio.sleep(self._timing.human_delay())
                        count += 1
                except Exception:
                    pass
            if count:
                logger.info("Objectives claimed: {}", count)
        except Exception as exc:
            logger.debug("claim_objectives error: {}", exc)
        return count

    async def _claim_section(self, nav_selector: str, claim_selector: str, label: str) -> int:
        """Generic claim helper: navigate to section, click all claim buttons."""
        await asyncio.sleep(self._timing.human_delay())
        page = self._nav._browser.page
        if page is None:
            return 0
        try:
            await page.click(nav_selector, timeout=6_000)
            await asyncio.sleep(self._timing.human_delay())
        except Exception as exc:
            logger.debug("_claim_section nav({}) failed: {}", label, exc)
            return 0
        count = 0
        try:
            btns = await page.locator(claim_selector).all()
            for btn in btns:
                try:
                    if await btn.is_enabled(timeout=1_000):
                        await btn.click()
                        await asyncio.sleep(self._timing.human_delay())
                        count += 1
                except Exception:
                    pass
            if count:
                logger.info("{} rewards claimed: {}", label, count)
        except Exception as exc:
            logger.debug("_claim_section({}) error: {}", label, exc)
        return count
