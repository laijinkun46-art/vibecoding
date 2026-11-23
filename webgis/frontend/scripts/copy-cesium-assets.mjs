import { cp, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const source = path.join(root, 'node_modules/cesium/Build/Cesium')
const destination = path.join(root, 'public/cesium')
await mkdir(destination, { recursive: true })
for (const name of ['Workers', 'ThirdParty', 'Assets', 'Widgets']) {
  await cp(path.join(source, name), path.join(destination, name), { recursive: true })
}
console.log('Cesium 本地静态资源已准备。')
