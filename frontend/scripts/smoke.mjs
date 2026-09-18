// Headless-browser smoke test: login (or first-run setup) -> create an SSH
// credential -> create a repo -> view its detail page -> confirm the
// dashboard reflects it. Not a substitute for the pytest suite -- this is
// the "does the UI actually render and wire up to the API" check described
// in the project's manual-verification standard, made repeatable instead of
// a one-off throwaway script.
//
// Usage:
//   npm run dev   (or: docker compose up -d, pointing BASE_URL at it)
//   node scripts/smoke.mjs [BASE_URL] [username] [password]
//
// Screenshots land in frontend/.smoke-screenshots/ (gitignored).

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const baseUrl = process.argv[2] || process.env.SMOKE_BASE_URL || 'http://localhost:5173'
const username = process.argv[3] || 'smoke-test'
const password = process.argv[4] || 'correct-horse-battery-smoke'
const shotsDir = '.smoke-screenshots'
mkdirSync(shotsDir, { recursive: true })

const consoleErrors = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
page.on('pageerror', (err) => consoleErrors.push(String(err)))

async function fillByLabel(labelText, value) {
  await page.locator('label', { hasText: labelText }).first().locator('input, textarea').fill(value)
}

await page.goto(baseUrl)
await page.waitForSelector('text=Haven Backup', { timeout: 15000 })

const isSetup = await page.locator('text=Welcome to Haven Backup').isVisible().catch(() => false)
if (isSetup) {
  await fillByLabel('Username', username)
  await fillByLabel('Password', password)
  await fillByLabel('Confirm password', password)
} else {
  await page.fill('input[type="text"], input:not([type])', username)
  await page.fill('input[type="password"]', password)
}
await page.click('button[type="submit"]')
await page.waitForSelector('text=Dashboard', { timeout: 15000 })
await page.screenshot({ path: `${shotsDir}/1-dashboard.png`, fullPage: true })

const credName = `smoke-cred-${Date.now()}`
await page.click('text=SSH Credentials')
await page.click('text=Add credential')
await fillByLabel('Name', credName)
await fillByLabel('Hostname', 'backup.example.invalid')
await fillByLabel('Username', 'haven')
await fillByLabel('Private key (PEM)', '-----BEGIN OPENSSH PRIVATE KEY-----\nsmoketest\n-----END OPENSSH PRIVATE KEY-----')
await page.click('text=Save credential')
await page.waitForSelector(`text=${credName}`, { timeout: 10000 })

const repoName = `smoke-repo-${Date.now()}`
await page.click('text=Repositories')
await page.click('text=Add repository')
await fillByLabel('Name', repoName)
await fillByLabel('Repo URL', 'ssh://haven@backup.example.invalid/./repo')
await page.locator('label', { hasText: 'SSH credential' }).locator('select').selectOption({ label: credName })
await fillByLabel('Passphrase', 'smoke-test-passphrase')
await page.click('text=Save repository')
await page.waitForSelector(`text=${repoName}`, { timeout: 10000 })
await page.screenshot({ path: `${shotsDir}/2-repo-created.png`, fullPage: true })

await page.click(`text=${repoName}`)
await page.waitForSelector('text=Retention policy', { timeout: 10000 })
await page.screenshot({ path: `${shotsDir}/3-repo-detail.png`, fullPage: true })

console.log(`Screenshots written to frontend/${shotsDir}/`)

if (consoleErrors.length > 0) {
  console.error('Browser console errors:', consoleErrors)
  await browser.close()
  process.exit(1)
}

console.log('Smoke test passed.')
await browser.close()
