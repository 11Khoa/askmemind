// Test-only static host: apply declared production rewrites, with no implicit
// Vite SPA fallback that could hide a missing route in vercel.json.
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { resolve, extname, sep } from 'node:path'

const root = resolve('dist')
const config = JSON.parse(await readFile('vercel.json', 'utf8'))
const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.pdf': 'application/pdf' }
createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
    const rewrite = config.rewrites.find((rule) => rule.source === pathname)
    const file = resolve(root, '.' + (rewrite?.destination || (pathname === '/' ? '/index.html' : pathname)))
    if (!file.startsWith(root + sep) || !(await stat(file)).isFile()) throw new Error('Not found')
    response.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream' })
    response.end(await readFile(file))
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain' })
    response.end('NOT_FOUND')
  }
}).listen(5184, '127.0.0.1')
