import { c } from "naive-ui"

// src/lib/motionClient.ts
type PoseListener = (t_ms: number, q: number[]) => void
type PrefetchListener = (t0_ms: number, step_ms: number, poses: number[][]) => void
type OpenListener = () => void
type ErrorListener = (e: any) => void

export class MotionClient {
    private ws: WebSocket | null = null
    private url: string
    private onPoseListeners: PoseListener[] = []
    private onPrefetchListeners: PrefetchListener[] = []
    private onOpenListeners: OpenListener[] = []
    private onErrorListeners: ErrorListener[] = []
    private _connected = false
    // private _reconnect = 0

    // 프론트에서 사용할 최신 project 스냅샷(필요 시 jointNames 참고)
    private _lastProject: any | null = null

    constructor(url: string) { this.url = url }

    get connected() { return this._connected }
    get lastProject() { return this._lastProject }

    connect() {
        if (this.ws) try { this.ws.close() } catch { }
        this.ws = new WebSocket(this.url)

        this.ws.onopen = () => {
            this._connected = true
            // this._reconnect = 0
            this.onOpenListeners.forEach(f => f())
        }
        this.ws.onerror = (e) => {
            this.onErrorListeners.forEach(f => f(e))
        }
        this.ws.onclose = () => {
            this._connected = false
            // if (this._reconnect < 5) { // 최대 연속 5번까지 재시도를 수행하고 그래도 연결이 안되면 종료
            //     this._reconnect += 1
            //     setTimeout(() => this.connect(), 1000)
            // }
        }
        this.ws.onmessage = (ev) => {
            try {
                const msg = JSON.parse(ev.data)
                if (msg.type === 'pose' && Array.isArray(msg.q)) {
                    this.onPoseListeners.forEach(f => f(msg.t_ms ?? 0, msg.q))
                } else if (msg.type === 'prefetch_result' && Array.isArray(msg.poses)) {
                    this.onPrefetchListeners.forEach(f => f(msg.t0_ms, msg.step_ms, msg.poses))
                }
            } catch { }
        }
    }

    onPose(cb: PoseListener) {
        this.onPoseListeners.push(cb); return () => {
            this.onPoseListeners = this.onPoseListeners.filter(f => f !== cb)
        }
    }
    onPrefetch(cb: PrefetchListener) {
        this.onPrefetchListeners.push(cb); return () => {
            this.onPrefetchListeners = this.onPrefetchListeners.filter(f => f !== cb)
        }
    }
    onOpen(cb: OpenListener) {
        this.onOpenListeners.push(cb); return () => {
            this.onOpenListeners = this.onOpenListeners.filter(f => f !== cb)
        }
    }
    onError(cb: ErrorListener) {
        this.onErrorListeners.push(cb); return () => {
            this.onErrorListeners = this.onErrorListeners.filter(f => f !== cb)
        }
    }

    setProject(projectSnapshot: any) {
        this._lastProject = projectSnapshot
        this._send({ type: 'set_project', project: projectSnapshot })
    }
    seek(t_ms: number) {
        // console.log('Seeking to:', t_ms)
        this._send({ type: 'seek', t_ms: Math.max(0, Math.round(t_ms)) })
    }
    prefetch(center_ms: number, window_ms = 4000, step_ms = 16.67) {
        this._send({ type: 'prefetch', center_ms, window_ms, step_ms })
    }

    private _send(obj: any) {
        const s = this.ws
        if (!s || s.readyState !== WebSocket.OPEN) return
        s.send(JSON.stringify(obj))
    }
}

export function throttle<T extends (...a: any[]) => void>(
    fn: T,
    ms: number
): (...args: Parameters<T>) => void {
    let last = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let queuedArgs: Parameters<T> | null = null;
    let lastThis: ThisParameterType<T> | undefined;

    function invoke(now: number) {
        last = now;
        // this와 인자를 보존해서 호출
        fn.apply(lastThis as any, queuedArgs as any);
        queuedArgs = null;
        lastThis = undefined;
    }

    return function throttled(this: ThisParameterType<T>, ...args: Parameters<T>) {
        const now = (typeof performance !== 'undefined' && performance.now)
            ? performance.now()
            : Date.now();

        queuedArgs = args;         // 마지막 인자 보관
        lastThis = this;           // this 보관

        const remain = ms - (now - last);

        if (remain <= 0) {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            invoke(now);             // 즉시 실행
        } else if (!timer) {
            timer = setTimeout(() => {
                timer = null;
                // 지연으로 늦어졌더라도 다음 윈도우 기준으로 last 갱신
                invoke((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now());
            }, remain);
        }
    };
}
