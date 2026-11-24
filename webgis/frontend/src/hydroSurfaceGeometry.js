// Vertices are keyed by the model's finest geographic lattice, not the packed frame texture.
export function makeSurfaceMesh(lookup, cols, rows, count) {
  const extents = Array.from({ length: count }, () => [cols, rows, -1, -1])
  const cellAt = (x, y) => x < 0 || x >= cols || y < 0 || y >= rows ? -1 : lookup[y * cols + x]
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
    const box = extents[cellAt(x, y)]
    box[0] = Math.min(box[0], x)
    box[1] = Math.min(box[1], y)
    box[2] = Math.max(box[2], x + 1)
    box[3] = Math.max(box[3], y + 1)
  }

  const grid = [], owners = [], neighbors = [], triangles = []
  function vertex(x, y, owner, stencil) {
    const index = owners.length
    grid.push(x, y)
    owners.push(owner)
    neighbors.push(...stencil)
    return index
  }
  extents.forEach(([w, s, e, n], owner) => {
    if (e <= w || n <= s) throw new Error('模型单元缺少空间索引')
    for (let y = s; y < n; y++) for (let x = w; x < e; x++) {
      if (cellAt(x, y) !== owner) throw new Error('显示网格需要有效的矩形模型单元')
    }
    const center = vertex((w + e) / 2, (s + n) / 2, owner, [owner, owner, owner, owner])
    const corner = (x, y) => vertex(x, y, owner, [
      cellAt(x - 1, y - 1), cellAt(x, y - 1), cellAt(x, y), cellAt(x - 1, y),
    ])
    // Close each coarse edge at the same lattice nodes used by its finer neighbours.
    const first = owners.length
    for (let x = w; x < e; x++) if (x === w || cellAt(x - 1, s - 1) !== cellAt(x, s - 1)) corner(x, s)
    for (let y = s; y < n; y++) if (y === s || cellAt(e, y - 1) !== cellAt(e, y)) corner(e, y)
    for (let x = e; x > w; x--) if (x === e || cellAt(x - 1, n) !== cellAt(x, n)) corner(x, n)
    for (let y = n; y > s; y--) if (y === n || cellAt(w - 1, y - 1) !== cellAt(w - 1, y)) corner(w, y)
    for (let i = first; i < owners.length; i++) triangles.push(center, i, i + 1 < owners.length ? i + 1 : first)
  })
  return {
    grid: new Float32Array(grid),
    owners: new Float32Array(owners),
    neighbors: new Float32Array(neighbors),
    triangles: owners.length > 65535 ? new Uint32Array(triangles) : new Uint16Array(triangles),
  }
}

