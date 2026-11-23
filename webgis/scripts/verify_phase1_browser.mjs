// 复用本机已有 Playwright 与 Edge，不安装浏览器或新增应用依赖。
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const modulePath = process.env.PLAYWRIGHT_MODULE_PATH
const { chromium } = await import(modulePath ? pathToFileURL(path.join(modulePath, 'index.mjs')).href : 'playwright')
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const failures = []
const badResponses = []
const checks = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 })
  page.on('pageerror', (error) => failures.push(error.message))
  page.on('response', (response) => { if (response.status() >= 400) badResponses.push({ url: response.url(), status: response.status() }) })
  await page.goto(process.env.WEBGIS_FRONTEND_URL || 'http://127.0.0.1:4173', { waitUntil: 'networkidle' })
  await page.locator('.connection-status.connected').waitFor({ timeout: 15000 })
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')].find((element) => element.textContent.trim() === '定位研究区')
    return button && !button.disabled
  }, undefined, { timeout: 20000 })
  await page.waitForFunction(() => document.querySelector('.cesium-map')?.dataset.pendingTiles === '0', undefined, { timeout: 30000 })
  assert.equal(await page.locator('.map-error').count(), 0)
  assert.equal(await page.locator('canvas').count(), 1)
  assert.match(await page.locator('.area-number').innerText(), /286\.55/)
  assert.equal(await page.locator('.cesium-map').getAttribute('data-scene-mode'), '3')
  assert.ok(Number(await page.locator('.cesium-map').getAttribute('data-camera-pitch')) > -1.2, '三维视角应为倾斜视角')
  checks.push('项目资料连接、真实面积和 Cesium 初始化通过')
  await page.screenshot({ path: path.join(root, 'outputs/phase1_desktop.png'), fullPage: true })
  await page.getByRole('button', { name: '二维', exact: true }).click()
  assert.equal(await page.getByRole('button', { name: '二维', exact: true }).getAttribute('aria-pressed'), 'true')
  assert.equal(await page.locator('.cesium-map').getAttribute('data-scene-mode'), '2')
  await page.getByRole('button', { name: '三维', exact: true }).click()
  await page.getByRole('button', { name: '定位研究区', exact: true }).click()
  checks.push('二维/三维切换与返回研究区无渲染错误')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForLoadState('networkidle')
  await page.waitForFunction(() => document.querySelector('.cesium-map')?.dataset.pendingTiles === '0')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: path.join(root, 'outputs/phase1_mobile.png'), fullPage: true })
  checks.push('390px 移动布局没有横向溢出')
  await page.route('**/api/**', (route) => route.abort('failed'))
  await page.reload({ waitUntil: 'networkidle' })
  await page.locator('.connection-error').waitFor()
  assert.match(await page.locator('.connection-status').innerText(), /服务连接失败/)
  await page.unroute('**/api/**')
  await page.getByRole('button', { name: '重新连接' }).click()
  await page.locator('.connection-status.connected').waitFor()
  checks.push('后端不可用时提示清楚，恢复连接后重试成功')
  await page.locator('select').selectOption('local')
  await page.waitForFunction(() => document.querySelector('.cesium-map')?.dataset.pendingTiles === '0')
  assert.equal(await page.locator('.map-error').count(), 0)
  checks.push('在线街道与本地概览切换通过')
  assert.deepEqual(failures, [], '浏览器发生脚本异常')
  assert.deepEqual(badResponses, [], '页面或 Cesium 静态资源 HTTP 失败')
  await writeFile(path.join(root, 'docs/phase1_browser_checks.json'), JSON.stringify({ passed: true, browser: await browser.version(), checks, pageErrors: failures, badResponses }, null, 2))
  console.log(JSON.stringify({ passed: true, checks }, null, 2))
} finally {
  await browser.close()
}
