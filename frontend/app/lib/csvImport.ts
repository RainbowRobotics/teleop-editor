// frontend/utils/csvImport.ts
import Papa from 'papaparse'

export type SourceNoId = {
  jointNames: string[]
  dt: number
  frames: number[][]
  name: string
}

export function importCsv(
  file: File,
  opts?: { dtFallback?: number }
): Promise<SourceNoId> {
  const dtFallback = opts?.dtFallback ?? 0.01
  const defaultName = file.name.replace(/\.[^.]+$/, '')

  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      worker: true,
      complete: (res) => {
        try {
          const rows = (res.data as any[]).filter(Boolean)
          if (!rows.length) throw new Error('CSV has no data rows.')

          const rawKeys = Object.keys(rows[0]).map((k) => (k ?? '').toString().trim())
          if (!rawKeys.length) throw new Error('Failed to read header columns.')

          const timeKey = rawKeys.find((k) => k.toLowerCase() === 'time')
          const jointNames = rawKeys.filter((k) => k !== timeKey)

          let dt = dtFallback
          if (timeKey) {
            let firstT: number | null = null
            let secondT: number | null = null
            for (let i = 0; i < rows.length; i++) {
              const t = Number((rows[i] ?? {})[timeKey])
              if (!isFinite(t)) continue
              if (firstT === null) { firstT = t; continue }
              if (secondT === null) { secondT = t; break }
            }
            if (firstT !== null && secondT !== null) {
              const diff = Math.abs(secondT - firstT)
              if (isFinite(diff) && diff > 0) dt = diff
            }
          }

          const frames: number[][] = rows.map((r) =>
            jointNames.map((jn) => {
              const v = r?.[jn]
              const n = Number(v)
              return Number.isFinite(n) ? n : 0
            })
          )

          resolve({
            name: defaultName, // 기본 이름
            jointNames,
            dt,
            frames,
          })
        } catch (err) {
          reject(err)
        }
      },
      error: (err) => reject(err),
    })
  })
}
