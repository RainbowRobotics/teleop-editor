<template>
    <div ref="root" class="mini-robot-root"></div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import URDFLoader from 'urdf-loader'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
import { ColladaLoader } from 'three/examples/jsm/loaders/ColladaLoader'
import { useProjectStore } from '@/stores/project'
import { useRobotCache } from '@/composable/useRobotModelCache'

const props = defineProps({
    source: { type: Object, required: true },  // frames: number[][]
    frame: { type: Number, required: true },
    height: { type: Number, default: null },   // 고정 높이(px) 없으면 aspect로 자동
    aspect: { type: Number, default: 16 / 9 }, // w/h
    modelName: { type: String, required: true },
    modelVersion: { type: String, required: true },
})

const root = ref(null)
let scene = null, camera = null, renderer = null, controls = null
let resizeObs = null, parentObs = null, io = null
let robot = null
const urdfJointMap = new Map()

const project = useProjectStore()
const { getModel, setModel, isLoaded, setLoaded, getShowCoordinates } = useRobotCache()

let disposed = false
let needsRender = false
function requestRender() {
    if (needsRender || disposed) return
    needsRender = true
    requestAnimationFrame(() => {
        needsRender = false
        if (renderer && scene && camera) renderer.render(scene, camera)
    })
}

/* ---------- helpers ---------- */
function nearestHostEl() {
    const el = root.value
    if (!el) return null
    // dialog 내부 레이아웃 기준을 갖고 있을 법한 조상
    return el.closest('.crop-dialog') || el.parentElement || el
}

async function ensureMeasured(maxTries = 10) {
    for (let i = 0; i < maxTries; i++) {
        const host = nearestHostEl()
        const w = host ? Math.floor(host.clientWidth || host.getBoundingClientRect().width) : 0
        if (w > 0) return true
        await new Promise(r => requestAnimationFrame(r))
    }
    return false
}

function bakeJointMap(rootObj) {
    urdfJointMap.clear()
    rootObj?.traverse?.((child) => {
        if (child.type === 'URDFJoint' || child.isURDFJoint) {
            urdfJointMap.set(child.name, child)
        }
    })
}

function addCoordinateHelpers(rootObj) {
    if (!getShowCoordinates()) return
    rootObj?.traverse?.((child) => {
        if (child.type === 'URDFLink' && !child.userData?._miniAxes) {
            const mk = (color, axis) => {
                const geom = new THREE.CylinderGeometry(0.004, 0.004, 0.18, 8)
                const mat = new THREE.MeshBasicMaterial({ color })
                const m = new THREE.Mesh(geom, mat)
                m.position.copy(axis.clone().multiplyScalar(0.09))
                m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis)
                return m
            }
            const g = new THREE.Group()
            g.add(mk(0xff5555, new THREE.Vector3(1, 0, 0)))
            g.add(mk(0x55ff55, new THREE.Vector3(0, 1, 0)))
            g.add(mk(0x5555ff, new THREE.Vector3(0, 0, 1)))
            child.add(g)
            child.userData._miniAxes = g
        }
    })
}

function applyPoseFromFrame(idx) {
    const frames = props.source?.frames
    const names = project.jointNames
    if (!frames?.length || !names?.length) return
    if (idx < 0 || idx >= frames.length) return
    const q = frames[idx]
    for (let i = 0; i < names.length && i < q.length; i++) {
        const name = names[i]
        const joint = urdfJointMap.get(name)
        if (!joint) continue
        try { joint.setJointValue(q[i]) } catch { }
    }
    requestRender()
}

/* ---------- sizing ---------- */
function readHostSize() {
    const host = nearestHostEl() || root.value
    const w = Math.max(1, Math.floor(host.clientWidth || host.getBoundingClientRect().width || 1))
    let h
    if (props.height != null) {
        h = Math.max(1, Math.floor(props.height))
    } else {
        h = Math.max(1, Math.floor(w / (props.aspect || (16 / 9))))
    }
    return { w, h }
}

function resizeNow() {
    if (!root.value || !renderer || !camera) return
    const { w, h } = readHostSize()

    // 컨테이너 자체 높이도 맞춰줌 (부모 폭 기준)
    root.value.style.height = `${h}px`

    // 카메라/렌더러 CSS 크기 = 부모 기준
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h, false)

    // 캔버스가 절대배치로 꽉 차도록 (안전벨트)
    const c = renderer.domElement
    c.style.position = 'absolute'
    c.style.inset = '0'
    c.style.width = '100%'
    c.style.height = '100%'

    requestRender()
}

/* ---------- lifecycle ---------- */
onMounted(async () => {
    await nextTick()
    if (!root.value) return

    // 부모가 레이아웃 잡을 때까지 대기 (0폭 방지)
    await ensureMeasured()

    // Scene / Camera / Renderer
    scene = new THREE.Scene()
    scene.background = new THREE.Color(0x212121)

    camera = new THREE.PerspectiveCamera(40, 1, 0.05, 100)
    camera.up.set(0, 0, 1)
    camera.position.set(2, 2, 0.6)
    camera.lookAt(0, 0, 1)

    renderer = new THREE.WebGLRenderer({
        antialias: false,
        powerPreference: 'high-performance',
        precision: 'highp',
    })
    // 고해상도에서도 CSS 크기는 부모 기준으로만 보이게
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    root.value.appendChild(renderer.domElement)

    // OrbitControls
    controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 0, 0.8)
    controls.enableRotate = true
    controls.enablePan = true
    controls.enableZoom = true
    controls.update()
    controls.addEventListener('change', requestRender)

    // Lights
    scene.add(new THREE.AmbientLight(0xdddddd, 0.45))
    const dir = new THREE.DirectionalLight(0xffffff, 0.8)
    dir.position.set(2.5, 2.5, 2.5)
    scene.add(dir)

        // 얇은 바닥
        ; (function () {
            const size = 6, divisions = 6
            const canvas = document.createElement('canvas')
            const ctx = canvas.getContext('2d')
            canvas.width = canvas.height = 512
            ctx.strokeStyle = '#666'; ctx.lineWidth = 1
            const step = canvas.width / divisions
            for (let i = 0; i <= divisions; i++) {
                const p = i * step + 0.5
                ctx.beginPath(); ctx.moveTo(p, 0); ctx.lineTo(p, canvas.height); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(0, p); ctx.lineTo(canvas.width, p); ctx.stroke()
            }
            const texture = new THREE.CanvasTexture(canvas)
            texture.wrapS = texture.wrapT = THREE.RepeatWrapping
            texture.repeat.set(size, size)
            const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true })
            const geometry = new THREE.PlaneGeometry(size, size)
            const grid = new THREE.Mesh(geometry, material)
            // grid.rotation.x = Math.PI / 2
            scene.add(grid)
        })()

    // 로더
    const gltfLoader = new GLTFLoader()
    const daeLoader = new ColladaLoader()
    const loader = new URDFLoader()
    loader.packages = ''
    loader.loadMeshCb = (path, manager, done) => {
        const base = path.replace(/\.[^/.]+$/, '')
        const glbPath = `${base}.glb`
        fetch(glbPath, { method: 'HEAD' })
            .then((res) => {
                if (res.ok) {
                    gltfLoader.load(glbPath, (gltf) => done(gltf.scene), undefined, () => {
                        daeLoader.load(path, (dae) => done(dae.scene))
                    })
                } else {
                    daeLoader.load(path, (dae) => done(dae.scene))
                }
            })
            .catch(() => {
                daeLoader.load(path, (dae) => done(dae.scene))
            })
    }

    const urdfPath =
        props.modelVersion === 'v1.0'
            ? `/models/rby1${props.modelName}/urdf/model.urdf`
            : `/models/rby1${props.modelName}/urdf/model_${props.modelVersion}.urdf`

    // 캐시 모델 → clone(true)
    const cached = getModel()
    if (isLoaded() && cached) {
        robot = cached.clone(true)
        robot.userData.__fromCacheClone = true
        scene.add(robot)
        addCoordinateHelpers(robot)
        bakeJointMap(robot)
        applyPoseFromFrame(props.frame)
    } else {
        loader.load(urdfPath, (urdf) => {
            urdf.userData.__cacheRoot = true
            setModel(urdf); setLoaded(true)

            robot = urdf.clone(true)
            robot.userData.__fromCacheClone = true
            scene.add(robot)
            addCoordinateHelpers(robot)
            bakeJointMap(robot)
            applyPoseFromFrame(props.frame)
            requestRender()
        })
    }

    // 최초 사이즈 맞추기
    resizeNow()

    // 관찰자들: 자신의 크기 + 가까운 부모(=dialog) 변화도 감지
    resizeObs = new ResizeObserver(resizeNow)
    resizeObs.observe(root.value)

    const host = nearestHostEl()
    if (host && host !== root.value) {
        parentObs = new ResizeObserver(resizeNow)
        parentObs.observe(host)
    }

    // 보이기 시작할 때에도 강제 리사이즈 (dialog 오픈 타이밍 대응)
    io = new IntersectionObserver((entries) => {
        if (entries.some(e => e.isIntersecting)) resizeNow()
    })
    io.observe(root.value)

    requestRender()
})

watch(() => props.frame, (f) => applyPoseFromFrame(f))
watch(() => props.source, () => applyPoseFromFrame(props.frame))

onBeforeUnmount(() => {
    disposed = true
    try { resizeObs && root.value && resizeObs.unobserve(root.value) } catch { }
    try { parentObs && parentObs.disconnect && parentObs.disconnect() } catch { }
    try { io && io.disconnect && io.disconnect() } catch { }
    try { controls && controls.dispose && controls.dispose() } catch { }
    try { renderer && renderer.dispose && renderer.dispose() } catch { }
    scene = null; camera = null; renderer = null; controls = null; robot = null
})
</script>

<style scoped>
.mini-robot-root {
    position: relative;
    /* 캔버스를 내부에 가둠 */
    width: 100%;
    /* height는 JS로 style.height에 반영됨 */
    display: block;
    overflow: hidden;
    /* 혹시 모를 넘침 방지 */
}

/* 캔버스를 부모 박스에 딱 맞춤 */
.mini-robot-root>canvas {
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
    display: block;
}
</style>
