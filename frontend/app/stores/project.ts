// stores/project.ts
import { defineStore } from 'pinia'

export type BlendMode = 'override' | 'crossfade' | 'additive'
export type BlendCurve = 'linear' | 'smoothstep' | 'easeInOut'

export type Source = { id: string; dt: number; frames: number[][]; name?: string }
export type Blend = { mode: BlendMode; inMs: number; outMs: number; curve: BlendCurve; weight: number; priority: number }
export type Clip = { id: string; sourceId: string; t0: number; inFrame: number; outFrame: number; name?: string; blend: Blend }

function makeId(p: string) { return `${p}_${Math.random().toString(36).slice(2, 9)}` }

export type ProjectSnapshot = {
  lengthMs: number
  sources: Record<string, Source>
  clips: Clip[]
  player: { playing: boolean; t_ms: number; rate: number }
  jointNames: string[]                      // ★ project-level joint names (24 DOF)
  endpoints?: {
    robotAddress?: string
    questAddress?: string
  }
}

// ★ state 전체 타입 명시
export type ProjectState = {
  lengthMs: number
  sources: Record<string, Source>
  clips: Clip[]
  player: { playing: boolean; t_ms: number; rate: number }
  jointNames: string[]

  blendDefaults: Blend

  // 연결 관련
  localAddress: string
  robotAddress: string
  questAddress: string
  robotConnected: boolean
  questConnected: boolean

  // Quest
  questWS: WebSocket | null
  questTransportUp: boolean
  questLastSeq: number
  questStaleMs: number
  questHz: number
  _questStaleTimeout: any

  backendUrl: string
  robot: { address: string, connected: boolean, ready: boolean, busy: boolean, phase: null | 'connecting' | 'enabling' | 'disconnecting' }
  master: { connected: boolean, busy: boolean }
  gripper: { connected: boolean, homed: boolean, running: boolean, busy: boolean, target_n: [number, number] | null }
  teleop: { running: boolean, mode: 'position' | 'impedance', busy: boolean }

  selectedClipId: string | null

  graphJointMode: 'joint' | 'rms'
  graphJointIndex: number

  statusTimer: number | null
  statusIntervalMs: number
  statusRunning: boolean
  statusInFlight: boolean
}

export const useProjectStore = defineStore('project', {
  // ★ 반환 타입 명시로 noImplicitAny/추론 이슈 방지
  state: (): ProjectState => ({
    lengthMs: 0,
    sources: {},
    clips: [],
    player: { playing: false, t_ms: 0, rate: 1.0 },
    jointNames: [
      "gripper_finger_r1", "gripper_finger_l1", "torso_0", "torso_1", "torso_2", "torso_3",
      "torso_4", "torso_5", "right_arm_0", "right_arm_1", "right_arm_2", "right_arm_3",
      "right_arm_4", "right_arm_5", "right_arm_6", "left_arm_0", "left_arm_1", "left_arm_2",
      "left_arm_3", "left_arm_4", "left_arm_5", "left_arm_6", "head_0", "head_1"
    ],

    // ★ as-cast 불필요: 정확한 리터럴 값이라 Blend로 추론됨
    blendDefaults: { mode: 'override', inMs: 120, outMs: 120, curve: 'easeInOut', weight: 1.0, priority: 0 },

    // 연결 관련
    localAddress: '192.168.100.56',
    robotAddress: '192.168.30.1:50051',
    questAddress: '192.168.100.67',
    robotConnected: false,
    questConnected: false,

    // Quest 연결 상태
    questWS: null,
    questTransportUp: false,
    questLastSeq: -1,
    questStaleMs: 1000, // 1초
    questHz: 10, // 10Hz
    _questStaleTimeout: 0,

    // 선택: 백엔드 베이스 URL
    backendUrl: 'http://localhost:8001',
    robot: { address: '', connected: false, ready: false, busy: false, phase: null },
    master: { connected: false, busy: false },
    gripper: { connected: false, homed: false, running: false, target_n: null, busy: false },
    teleop: { running: false, mode: 'position', busy: false },

    selectedClipId: null,

    graphJointMode: 'joint' as 'joint' | 'rms',
    graphJointIndex: 0,

    statusTimer: null,
    statusIntervalMs: 1000,
    statusRunning: false,
    statusInFlight: false,
  }),

  getters: {
    // ★ state 타입 명시로 "Parameter 'state' implicitly has an 'any' type" 방지
    selectedClip: (state: ProjectState): Clip | null =>
      state.clips.find(c => c.id === state.selectedClipId) ?? null,
  },

  actions: {
    setBlendDefaults(patch: Partial<Blend>) {
      this.blendDefaults = { ...this.blendDefaults, ...patch }
    },

    setSelectedClip(id: string | null) {
      this.selectedClipId = id
    },

    /* ---------- 타임라인 데이터 ---------- */
    addSource(src: Omit<Source, 'id'> & { id?: string }) {
      const id = src.id ?? makeId('src')
      this.sources[id] = { ...src, id }
      return id
    },

    addClip(c: Omit<Clip, 'id'> & { id?: string }) {
      const id = c.id ?? makeId('clip')
      const clip: Clip = { ...c, id }
      this.clips.push(clip)
      const s = this.sources[clip.sourceId]
      if (s) {
        const dur = Math.round((clip.outFrame - clip.inFrame) * s.dt * 1000)
        this.lengthMs = Math.max(this.lengthMs, clip.t0 + dur)
      }
      return id
    },

    addClipFromSource(sourceId: string, opts: {
      inFrame: number; outFrame: number; t0?: number; name?: string; blend?: Partial<Blend>
    }) {
      const s = this.sources[sourceId]
      if (!s) throw new Error('source not found: ' + sourceId)

      const inF = Math.max(0, Math.min(opts.inFrame, s.frames.length - 1))
      const outF = Math.max(inF + 1, Math.min(opts.outFrame, s.frames.length))
      const t0 = opts.t0 ?? this.lengthMs
      const blend: Blend = { ...this.blendDefaults, ...(opts.blend ?? {}) }

      return this.addClip({ sourceId, inFrame: inF, outFrame: outF, t0, name: opts.name, blend })
    },

    updateSourceName(id: string, name: string) {
      const s = this.sources[id]; if (!s) return
      this.sources[id] = { ...s, name: (name || '').trim() }
    },

    updateClipBlend(clipId: string, patch: Partial<Blend>) {
      const c = this.clips.find(c => c.id === clipId); if (!c) return
      c.blend = { ...c.blend, ...patch }
    },

    /* ---------- 프로젝트 저장/로드 ---------- */
    toSnapshot(): ProjectSnapshot {
      return {
        lengthMs: this.lengthMs,
        sources: this.sources,
        clips: this.clips,
        player: this.player,
        jointNames: this.jointNames, // ★ 반드시 포함
        endpoints: { robotAddress: this.robotAddress, questAddress: this.questAddress }
      }
    },

    fromSnapshot(p: ProjectSnapshot) {
      this.lengthMs = p.lengthMs ?? 0
      this.sources = p.sources ?? {}
      this.clips = p.clips ?? []
      this.player = p.player ?? { playing: false, t_ms: 0, rate: 1.0 }
      // ★ jointNames 반영 누락 보정
      if (Array.isArray(p.jointNames) && p.jointNames.length > 0) {
        this.jointNames = p.jointNames
      }
      if (p.endpoints) {
        this.robotAddress = p.endpoints.robotAddress ?? this.robotAddress
        this.questAddress = p.endpoints.questAddress ?? this.questAddress
      }
    },

    // 로컬 파일 저장
    saveProjectToFile() {
      const blob = new Blob([JSON.stringify(this.toSnapshot(), null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `project_${new Date().toISOString().replace(/[:.]/g, '-')}.json`
      a.click()
      URL.revokeObjectURL(a.href)
    },

    // 로컬 파일 로드
    async loadProjectFromFile(file: File) {
      const text = await file.text()
      const snap = JSON.parse(text) as ProjectSnapshot
      this.fromSnapshot(snap)
    },

    // (선택) 백엔드 저장/로드
    async saveProjectToBackend() {
      await fetch(this.backendUrl + '/api/project', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.toSnapshot())
      })
    },

    async loadProjectFromBackend() {
      const r = await fetch(this.backendUrl + '/api/project')
      const p = await r.json() as ProjectSnapshot
      this.fromSnapshot(p)
    },

    /* ---------- 연결/제어 ---------- */

    async connectQuest() {
      this.ensureQuestWS();

      const [quest_ip, quest_port_str] = this.questAddress.split(':');
      const [local_ip, local_port_str] = this.localAddress.split(':');

      try {
        const r = await fetch(this.backendUrl + '/quest/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            local_ip,
            quest_ip,
            ...(local_port_str ? { local_port: Number(local_port_str) } : {}),
            ...(quest_port_str ? { quest_port: Number(quest_port_str) } : {}),
          }),
        });
        const j = await r.json().catch(() => ({} as any));
        const ok = r.ok && (j as any).ok !== false;
        if (!ok) this.questConnected = false;
      } catch (e) {
        console.error(e);
        this.questConnected = false;
      }
    },

    play() { this.player.playing = true },
    stop() { this.player.playing = false; this.player.t_ms = 0 },
    pause() { this.player.playing = false },

    /* ---------- Quest 연결 상태 관리 ---------- */
    ensureQuestWS() {
      if (this.questWS && this.questTransportUp) return;
      this.startQuestWS();
    },

    startQuestWS() {
      if (this.questWS && this.questTransportUp) return

      const wsBase = this.backendUrl.replace(/^http(s?):/, 'ws$1:')
      const wsUrl = `${wsBase}/ws/quest?hz=${this.questHz}`

      const ws = new WebSocket(wsUrl)
      this.questWS = ws

      const clearStale = () => {
        if (this._questStaleTimeout) {
          clearTimeout(this._questStaleTimeout)
          this._questStaleTimeout = 0
        }
      }
      const armStale = () => {
        clearStale()
        this._questStaleTimeout = setTimeout(() => {
          this.questConnected = false
        }, this.questStaleMs)
      }

      ws.onopen = () => {
        this.questTransportUp = true
        this.questConnected = false
        armStale()
      }

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          const seq = (msg?._server_seq ?? this.questLastSeq) as number
          if (seq > this.questLastSeq) {
            if (this.questLastSeq >= 0) this.questConnected = true
            this.questLastSeq = seq
            armStale()
          }
        } catch { /* ignore */ }
      }

      const down = () => {
        this.questTransportUp = false
        this.questConnected = false
        clearStale()
        this.questWS = null
      }
      ws.onerror = down
      ws.onclose = down
    },

    stopQuestWS() {
      try { this.questWS?.close() } catch { }
      this.questTransportUp = false
      this.questConnected = false
      this._clearQuestStaleTimeout()
    },

    _clearQuestStaleTimeout() {
      if (this._questStaleTimeout) {
        clearTimeout(this._questStaleTimeout)
        this._questStaleTimeout = 0
      }
    },

    setGraphJoint(idx: number) {
      this.graphJointIndex = Math.max(0, Math.min(23, Math.trunc(idx)))
    },
    setGraphMode(m: 'joint' | 'rms') { this.graphJointMode = m },

    // Robot
    async refreshRobot() {
      const r = await fetch(`${this.backendUrl}/robot/state`)
      const s = await r.json()
      // console.log(s) // TODO DEBUG
      this.robot.address = s.address ?? this.robot.address
      this.robot.connected = !!s.connected
      this.robot.ready = !!s.ready && !!s.power_all_on
    },

    // 3) Connect with busy/phase=connecting
    async connectRobot(address?: string) {
      this.robot.busy = true
      this.robot.phase = 'connecting'
      try {
        const body = { address: address ?? this.robot.address ?? '' }
        const r = await fetch(`${this.backendUrl}/robot/connect`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        })
        if (!r.ok) throw new Error(await r.text())
        await this.refreshRobot()
      } finally {
        this.robot.busy = false
        this.robot.phase = null
      }
    },

    // 4) Enable with busy/phase=enabling
    async enableRobot(mode: 'position' | 'impedance' = 'position') {
      if (!this.robot.connected) throw new Error('Robot not connected')
      this.robot.busy = true
      this.robot.phase = 'enabling'
      try {
        const r = await fetch(`${this.backendUrl}/robot/enable`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ control_mode: mode })
        })
        if (!r.ok) throw new Error(await r.text())
        await this.refreshRobot()
      } finally {
        this.robot.busy = false
        this.robot.phase = null
      }
    },

    // 5) Stop/Disconnect with busy/phase=disconnecting
    async stopRobot() {
      this.robot.busy = true
      this.robot.phase = 'disconnecting'
      try {
        await fetch(`${this.backendUrl}/robot/stop`, { method: 'POST' })
        await this.refreshRobot()
      } finally {
        this.robot.busy = false
        this.robot.phase = null
      }
    },
    async disconnectRobot() {
      this.robot.busy = true
      this.robot.phase = 'disconnecting'
      try {
        await fetch(`${this.backendUrl}/robot/disconnect`, { method: 'POST' })
        await this.refreshRobot()
      } finally {
        this.robot.busy = false
        this.robot.phase = null
      }
    },

    // 6) One-button flow now shows busy across both connect → enable
    async smartRobot(address?: string) {
      if (this.robot.busy) return
      // OFFLINE → CONNECT → ENABLE
      if (!this.robot.connected) {
        await this.connectRobot(address)
        await this.enableRobot(this.teleop?.mode ?? 'position')
        return
      }
      // CONNECTED/READY → STOP + DISCONNECT
      if (this.robot.connected) {
        await this.stopRobot()
        await this.disconnectRobot()
      }
    },

    // Master
    async refreshMaster() {
      const r = await fetch(`${this.backendUrl}/master/state`); const s = await r.json()
      this.master.connected = !!s.connected
    },
    async smartMaster() {
      if (this.master.busy) return; this.master.busy = true
      try {
        if (!this.master.connected) await fetch(`${this.backendUrl}/master/connect`, { method: 'POST' })
        else await fetch(`${this.backendUrl}/master/disconnect`, { method: 'POST' })
        await this.refreshMaster()
      } finally { this.master.busy = false }
    },

    // Gripper (for manual testing; teleop will run it automatically)
    async refreshGripper() {
      const r = await fetch(`${this.backendUrl}/gripper/state`); const s = await r.json()
      this.gripper.connected = !!s.connected; this.gripper.homed = !!s.homed; this.gripper.running = !!s.running
      this.gripper.target_n = Array.isArray(s.target_n) ? (s.target_n as [number, number]) : null
    },
    async smartGripper() {
      if (this.gripper.busy) return; this.gripper.busy = true
      try {
        if (!this.gripper.connected) {
          await fetch(`${this.backendUrl}/gripper/connect`, { method: 'POST' })
          await fetch(`${this.backendUrl}/gripper/homing`, { method: 'POST' })
          await fetch(`${this.backendUrl}/gripper/start`, { method: 'POST' })
        } else {
          await fetch(`${this.backendUrl}/gripper/stop`, { method: 'POST' })
          await fetch(`${this.backendUrl}/gripper/disconnect`, { method: 'POST' })
        }
        await this.refreshGripper()
      } finally { this.gripper.busy = false }
    },
    async setGripperNormalized(n: [number, number]) {
      await fetch(`${this.backendUrl}/gripper/target/n`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ n }),
      })
      this.gripper.target_n = n
    },

    // Teleop
    async refreshTeleop() {
      const r = await fetch(`${this.backendUrl}/teleop/state`); const s = await r.json()
      this.teleop.running = !!s.running; this.teleop.mode = s.mode ?? this.teleop.mode
    },
    async toggleTeleop() {
      if (this.teleop.busy) return; this.teleop.busy = true
      try {
        if (!this.teleop.running) {
          await fetch(`${this.backendUrl}/teleop/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: this.teleop.mode }) })
        } else {
          await fetch(`${this.backendUrl}/teleop/stop`, { method: 'POST' })
        }
        await this.refreshTeleop()
      } finally { this.teleop.busy = false }
    },

    // Polling
    async statusTick() {
      if (this.statusInFlight) return
      this.statusInFlight = true
      try {
        await Promise.allSettled([
          this.refreshRobot?.(),
          this.refreshMaster?.(),
          this.refreshTeleop?.(),
          this.refreshGripper?.(),
          // this.refreshQuestState?.(),   // TODO
        ])
      } finally {
        this.statusInFlight = false
      }
    },
  
    // Start polling (fires once immediately)
    startStatusPolling(intervalMs?: number) {
      if (this.statusTimer) return   // already running
      if (intervalMs) this.statusIntervalMs = intervalMs
      this.statusRunning = true
      // fire immediately so UI updates fast
      void this.statusTick()
      this.statusTimer = window.setInterval(() => this.statusTick(), this.statusIntervalMs)
    },
  
    // Stop polling
    stopStatusPolling() {
      this.statusRunning = false
      if (this.statusTimer) {
        clearInterval(this.statusTimer)
        this.statusTimer = null
      }
    },
  }
})
