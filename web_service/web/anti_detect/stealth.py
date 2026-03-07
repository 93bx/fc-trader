"""FC 26 WEB APP — JavaScript stealth injection patches for Playwright pages."""

from __future__ import annotations

import random

from loguru import logger

from web.config_loader import AntiDetectConfig


class StealthEngine:
    """Injects JS patches that reduce automation fingerprint signals."""

    def __init__(self, cfg: AntiDetectConfig) -> None:
        """Store anti-detection config and generate fixed per-session noise seed."""
        self._cfg = cfg
        self._session_noise = random.uniform(1.111111, 1.999999)

    async def inject(self, page) -> None:
        """Apply all stealth patches to a page before navigation."""
        await self._patch_webdriver(page)
        await self._patch_navigator(page)
        await self._patch_screen(page)
        await self._patch_timezone(page)
        await self._patch_webgl(page)
        await self._patch_canvas(page)
        await self._patch_audio(page)
        await self._patch_chrome_runtime(page)
        await self._patch_plugins(page)
        await self._patch_permissions(page)
        await self._patch_mouse_movement(page)

    async def _apply_script(self, page, js: str, name: str) -> None:
        """Apply one init script with logging."""
        try:
            await page.add_init_script(js)
            logger.debug("Stealth patch injected: {}", name)
        except Exception as exc:
            logger.debug("Stealth patch failed: {} | {}", name, exc)

    async def _patch_webdriver(self, page) -> None:
        js = """
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined,
});
delete navigator.__proto__.webdriver;
"""
        await self._apply_script(page, js, "webdriver")

    async def _patch_navigator(self, page) -> None:
        js = """
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'language', { get: () => 'ar-SA' });
Object.defineProperty(navigator, 'languages', { get: () => ['ar-SA','ar','en-US','en'] });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
Object.defineProperty(navigator, 'productSub', { get: () => '20030107' });
Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
"""
        await self._apply_script(page, js, "navigator")

    async def _patch_screen(self, page) -> None:
        js = """
Object.defineProperty(screen, 'width', { get: () => 1920 });
Object.defineProperty(screen, 'height', { get: () => 1080 });
Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
Object.defineProperty(window, 'devicePixelRatio', { get: () => 1.0 });
"""
        await self._apply_script(page, js, "screen")

    async def _patch_timezone(self, page) -> None:
        js = """
const origGetTimezoneOffset = Date.prototype.getTimezoneOffset;
Date.prototype.getTimezoneOffset = function() { return -180; };
const origResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
Intl.DateTimeFormat.prototype.resolvedOptions = function() {
  const options = origResolvedOptions.call(this);
  options.timeZone = 'Asia/Riyadh';
  return options;
};
"""
        await self._apply_script(page, js, "timezone")

    async def _patch_webgl(self, page) -> None:
        renderer = self._cfg.webgl_renderer
        vendor = self._cfg.webgl_vendor
        js = f"""
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {{
  if (param === 37446) return '{renderer}';
  if (param === 37445) return '{vendor}';
  return getParameter.call(this, param);
}};
const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function(param) {{
  if (param === 37446) return '{renderer}';
  if (param === 37445) return '{vendor}';
  return getParameter2.call(this, param);
}};
"""
        await self._apply_script(page, js, "webgl")

    async def _patch_canvas(self, page) -> None:
        js = f"""
const _sessionNoise = {self._session_noise:.8f};
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
  const ctx = this.getContext('2d');
  if (ctx) {{
    const pixel = ctx.getImageData(0, 0, 1, 1);
    pixel.data[0] = (pixel.data[0] + Math.floor(_sessionNoise * 2)) % 256;
    ctx.putImageData(pixel, 0, 0);
  }}
  return origToDataURL.call(this, type, quality);
}};
"""
        await self._apply_script(page, js, "canvas")

    async def _patch_audio(self, page) -> None:
        js = f"""
const origGetChannelData = AudioBuffer.prototype.getChannelData;
AudioBuffer.prototype.getChannelData = function(channel) {{
  const data = origGetChannelData.call(this, channel);
  for (let i = 0; i < data.length; i += 100) {{
    data[i] = data[i] + ({self._session_noise:.8f} * 1e-7);
  }}
  return data;
}};
"""
        await self._apply_script(page, js, "audio")

    async def _patch_chrome_runtime(self, page) -> None:
        js = """
if (!window.chrome) {
  window.chrome = {
    runtime: {
      onConnect: { addListener: () => {} },
      onMessage: { addListener: () => {} },
      connect: () => ({}),
      sendMessage: () => {},
      id: undefined,
    },
    loadTimes: () => ({}),
    csi: () => ({}),
    app: {},
  };
}
"""
        await self._apply_script(page, js, "chrome_runtime")

    async def _patch_plugins(self, page) -> None:
        js = """
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const plugins = [
      { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
      { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    ];
    plugins.length = 3;
    return Object.assign([], plugins, { item: (i) => plugins[i], namedItem: (n) => plugins.find(p => p.name === n) });
  }
});
"""
        await self._apply_script(page, js, "plugins")

    async def _patch_permissions(self, page) -> None:
        js = """
const origQuery = window.navigator.permissions.query.bind(navigator.permissions);
window.navigator.permissions.query = (parameters) => {
  if (parameters.name === 'notifications') return Promise.resolve({ state: 'granted' });
  return origQuery(parameters);
};
"""
        await self._apply_script(page, js, "permissions")

    async def _patch_mouse_movement(self, page) -> None:
        js = """
setInterval(() => {
  const x = Math.floor(Math.random() * 1800) + 60;
  const y = Math.floor(Math.random() * 900) + 60;
  document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: x, clientY: y }));
}, (Math.random() * 30000) + 15000);
"""
        await self._apply_script(page, js, "mouse_movement")

