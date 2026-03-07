"""FC 26 WEB APP — SBC auto-complete using club-only players."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from web.anti_detect.timing import KSATiming
from web.config_loader import WebConfig
from web.web_navigator import WebNavigator

if TYPE_CHECKING:
    from web.database_proxy import Database


class WebSBC:
    """Completes SBCs in configured target categories using club players only."""

    def __init__(
        self,
        navigator: WebNavigator,
        db: "Database",
        timing: KSATiming,
        cfg: WebConfig,
    ) -> None:
        """Store navigator, database, timing and config."""
        self._nav = navigator
        self._db = db
        self._timing = timing
        self._cfg = cfg

    async def run_sbc_cycle(self) -> int:
        """Attempt to complete all available target-category SBCs; returns count."""
        if not self._cfg.sbc.enabled:
            return 0
        if not await self._nav.go_to_sbc():
            logger.warning("Could not navigate to SBC hub.")
            return 0
        completed = 0
        sbcs = await self.get_available_sbcs()
        for sbc in sbcs:
            try:
                ok = await self.attempt_complete(sbc)
                if ok:
                    completed += 1
            except Exception as exc:
                logger.warning("SBC '{}' attempt raised: {}", sbc.get("name"), exc)
        return completed

    async def get_available_sbcs(self) -> list[dict]:
        """Parse SBC hub for entries matching target_categories config."""
        page = self._nav._browser.page
        if page is None:
            return []
        results: list[dict] = []
        try:
            cards = await page.locator("[class*='sbc-set'], [class*='challenge-set']").all()
            for card in cards:
                name = ""
                category = ""
                try:
                    name = await card.locator("[class*='title'], [class*='name']").first.inner_text(timeout=1_500)
                    category = await card.locator("[class*='category']").first.inner_text(timeout=1_500)
                except Exception:
                    pass
                if not any(cat.lower() in category.lower() for cat in self._cfg.sbc.target_categories):
                    continue
                results.append({"name": name.strip(), "category": category.strip()})
        except Exception as exc:
            logger.debug("get_available_sbcs error: {}", exc)
        return results

    async def attempt_complete(self, sbc: dict) -> bool:
        """Click into SBC, auto-build with club players, submit, claim reward."""
        page = self._nav._browser.page
        if page is None:
            return False
        sbc_name = sbc.get("name", "unknown")
        try:
            await page.click(
                f"[class*='sbc-set']:has-text('{sbc_name}'), "
                f"[class*='challenge-set']:has-text('{sbc_name}')",
                timeout=5_000,
            )
            await asyncio.sleep(self._timing.human_delay())

            squads = await page.locator("[class*='squad-slot'], [class*='sbc-squad']").all()
            for squad in squads:
                try:
                    auto_btn = squad.locator(
                        "button:has-text('Auto-Build'), button:has-text('Fill with Club Players')"
                    )
                    if await auto_btn.is_visible(timeout=2_000):
                        await auto_btn.click()
                        await asyncio.sleep(self._timing.human_delay())
                except Exception:
                    pass

            submit_btn = page.locator("button:has-text('Submit'), button:has-text('Complete')")
            if await submit_btn.is_visible(timeout=4_000):
                await submit_btn.click()
                await asyncio.sleep(self._timing.human_delay())

            try:
                await page.click("button:has-text('Claim')", timeout=4_000)
            except Exception:
                pass

            logger.info("SBC completed: {}", sbc_name)
            return True
        except Exception as exc:
            logger.debug("attempt_complete('{}') error: {}", sbc_name, exc)
            return False
