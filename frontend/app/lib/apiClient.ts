// src/lib/apiClient.ts
import { createDiscreteApi } from 'naive-ui'

/** ──────────────────────────────────────────────────────────────
 *  Discrete notification (컴포넌트 밖에서도 호출 가능)
 *  ────────────────────────────────────────────────────────────── */
const { notification } = createDiscreteApi(['notification'])
function notifyError(title: string, content?: string) {
    notification.error({ title, content, duration: 3500 })
}

/** ──────────────────────────────────────────────────────────────
 *  Base URL 관리
 *  ────────────────────────────────────────────────────────────── */
let BASE_URL = ''
export function setBaseUrl(url: string) {
    BASE_URL = (url || '').replace(/\/+$/, '')
}
export function getBaseUrl() {
    return BASE_URL
}

/** ──────────────────────────────────────────────────────────────
 *  공통 request: HTTP 의미론 표준화에 맞는 파서
 *   - 실패: !res.ok → detail 추출 후 notify + throw
 *   - 성공:
 *      • 204 → undefined
 *      • Content-Type=application/json → json()
 *      • Content-Type=text/csv → blob() (다운로드/파일)
 *      • Content-Type=text/* → text()
 *      • 그 외 → blob()
 *  ────────────────────────────────────────────────────────────── */
async function request<T = any>(path: string, init?: RequestInit): Promise<T> {
    const url = `${BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`
    let res: Response
    try {
        res = await fetch(url, init)
    } catch (e: any) {
        notifyError('Network error', e?.message || 'Failed to reach server')
        throw e
    }

    // 실패 처리
    if (!res.ok) {
        let detail = ''
        const ct = res.headers.get('content-type') || ''
        try {
            if (ct.includes('application/json')) {
                const j = await res.json()
                detail = j?.detail || JSON.stringify(j)
            } else {
                detail = await res.text()
            }
        } catch {
            /* ignore parse errors */
        }
        notifyError(`HTTP ${res.status}`, detail || 'Request failed')
        throw new Error(detail || `HTTP ${res.status}`)
    }

    // 성공 파싱
    if (res.status === 204) return undefined as T

    const ct = res.headers.get('content-type') || ''
    if (ct.includes('application/json')) return (await res.json()) as T
    if (ct.includes('text/csv')) return (await res.blob()) as T
    if (ct.startsWith('text/')) return (await res.text()) as T
    return (await res.blob()) as T
}

/** JSON POST helper */
function postJson<T = any>(path: string, body?: any, extra?: RequestInit) {
    return request<T>(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(extra?.headers || {}) },
        body: body != null ? JSON.stringify(body) : undefined,
        ...extra,
    })
}

/** 파일 저장 유틸 (CSV 등) */
export async function downloadBlobToFile(blob: Blob, filename: string) {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    document.body.appendChild(a)
    a.click()
    URL.revokeObjectURL(a.href)
    a.remove()
}

/** ──────────────────────────────────────────────────────────────
 *  API 집합
 *  ────────────────────────────────────────────────────────────── */
export const api = {
    /** Robot */
    robot: {
        state: () => request('/robot/state'),                                       // 200 JSON
        connect: (address: string) => postJson('/robot/connect', { address }),      // 204
        enable: (mode: 'position' | 'impedance' = 'position') =>
            postJson('/robot/enable', { control_mode: mode }),                        // 204
        stop: () => postJson('/robot/stop'),                                        // 204
        disconnect: () => postJson('/robot/disconnect'),                            // 204
    },

    /** Master (MasterArm) */
    master: {
        state: () => request('/master/state'),                                      // 200 JSON
        connect: () => postJson('/master/connect'),                                 // 204
        disconnect: () => postJson('/master/disconnect'),                           // 204
    },

    /** Gripper */
    gripper: {
        state: () => request('/gripper/state'),                                     // 200 JSON
        connect: () => postJson('/gripper/connect'),                                 // 204
        homing: () => postJson('/gripper/homing'),                                   // 204
        start: () => postJson('/gripper/start'),                                     // 204
        stop: () => postJson('/gripper/stop'),                                       // 204
        disconnect: () => postJson('/gripper/disconnect'),                           // 204
        setTargetN: (n: [number, number]) => postJson('/gripper/target/n', { n }),   // 204
    },

    /** Teleop */
    teleop: {
        state: () => request('/teleop/state'),                                      // 200 JSON
        start: (mode: 'position' | 'impedance') => postJson('/teleop/start', { mode }), // 204
        stop: () => postJson('/teleop/stop'),                                       // 204
    },

    /** Play */
    play: {
        state: () => request('/play/state'),                                        // 200 JSON
        start: (t0_ms: number) => postJson('/play/start', { t0_ms }),               // 204
        stop: () => postJson('/play/stop'),                                         // 204
        seek: (marker_ms: number) => postJson('/play/seek', { marker_ms }),         // 204
    },

    /** Record */
    record: {
        state: () => request('/record/state'),                                      // 200 JSON
        start: () => postJson('/record/start'),                                      // 204
        stop: () => postJson('/record/stop'),                                        // 204
        /** CSV 다운로드: 서버가 Content-Disposition으로 파일명 제공 */
        download: async () => {
            const path = '/record/download'
            const url = `${BASE_URL}${path}`
            let res: Response
            try {
                res = await fetch(url)
            } catch (e: any) {
                notifyError('Network error', e?.message || 'Failed to reach server')
                throw e
            }
            if (!res.ok) {
                let msg = ''
                const ct = res.headers.get('content-type') || ''
                try {
                    if (ct.includes('application/json')) msg = (await res.json())?.detail || ''
                    else msg = await res.text()
                } catch {/* ignore */ }
                notifyError(`HTTP ${res.status}`, msg || 'Download failed')
                throw new Error(msg || `HTTP ${res.status}`)
            }
            const blob = await res.blob()
            const fname =
                (res.headers.get('Content-Disposition') || '')
                    .match(/filename="([^"]+)"/)?.[1] || 'recording.csv'
            return { blob, filename: fname }
        },
        summary: () => request('/record/summary'),                                  // 200 JSON
    },

    /** Project (save/load) */
    project: {
        save: (p: any) => postJson('/api/project', p),                              // 204
        load: () => request('/api/project'),                                        // 200 JSON
    },

    /** Motion (CSV export via StreamingResponse) */
    motion: {
        exportCsv: (p: { t0_ms: number; t1_ms: number; step_ms: number; include_header?: boolean }) =>
            postJson<Blob>('/motion/export_csv', p),                                  // text/csv → blob
    },

    /** Quest (UDP announce/listener) */
    quest: {
        connect: (p: { local_ip: string; quest_ip: string; local_port?: number; quest_port?: number }) =>
            postJson('/quest/connect', p),                                            // 204
        disconnect: () => postJson('/quest/disconnect'),                            // 204
    },
}

export default api
