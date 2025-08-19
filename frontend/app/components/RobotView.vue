<template>
  <div class="viewer-wrapper">
    <div ref="paneContainer" class="tweak-pane-container" />
    <div ref="viewer" class="viewer-container" />
  </div>
</template>

<script setup>
/**
 * RobotView.vue (JavaScript)
 * - /ws/motion 에서 포즈(q[24]) 수신 → URDF 조인트에 반영
 * - project.jointNames 순서 기반 조인트 매핑
 * - 30Hz 업데이트 (requestRender 병합 렌더)
 * - GLB 우선, 실패 시 DAE로 메쉬 로드
 * - 전역 캐시(useRobotCache) 원본은 __cacheRoot 마킹하고 dispose 금지
 */
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import URDFLoader from 'urdf-loader'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
import { ColladaLoader } from 'three/examples/jsm/loaders/ColladaLoader'
import { Pane } from 'tweakpane'

import { useRobotCache } from '@/composable/useRobotModelCache'
import { useProjectStore } from '@/stores/project'
import { MotionClient } from '@/lib/motionClient'

/* ---------- refs / states ---------- */
const viewer = ref(null)
const paneContainer = ref(null)

const project = useProjectStore()
let motion = null

const lastPose = ref(null) // q[24]

// URDF joint map (name -> URDFJoint)
let urdfJointMap = new Map()

// UI / 렌더 옵션
const enableOrbit = ref(true)
const showCoordinates = ref(false)
const gridSize = ref(10)
const gridDiv = ref(5)

// Three.js
let scene, camera, renderer, controls
let gridMesh = null
let observer = null
let disposed = false

// 캐시된 로봇 모델
const { getModel, setModel, isLoaded, setLoaded, getShowCoordinates, setShowCoordinates } = useRobotCache()

// 30Hz
let lastUpdateTime = 0
const UPDATE_INTERVAL = 1000 / 30
let jointTimer = null

// 요청 병합형 렌더
let needsRender = false
function requestRender() {
  if (needsRender || disposed) return
  needsRender = true
  requestAnimationFrame(() => {
    needsRender = false
    renderNow()
  })
}
function renderNow() {
  if (disposed) return
  renderer.render(scene, camera)
}

/* ---------- helpers ---------- */
function createGridPlane(size = 10, divisions = 20) {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  canvas.width = canvas.height = 512
  ctx.strokeStyle = '#888'
  ctx.lineWidth = 1
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
  const mesh = new THREE.Mesh(geometry, material)
  return mesh
}

function createCustomAxes(length = 0.3) {
  const group = new THREE.Group()
  const addAxis = (dir, color) => {
    const mat = new THREE.MeshBasicMaterial({ color })
    const geom = new THREE.CylinderGeometry(0.003, 0.003, length, 8)
    const mesh = new THREE.Mesh(geom, mat)
    mesh.position.copy(dir.clone().multiplyScalar(length / 2))
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
    group.add(mesh)
  }
  addAxis(new THREE.Vector3(1, 0, 0), 0xff0000)
  addAxis(new THREE.Vector3(0, 1, 0), 0x00ff00)
  addAxis(new THREE.Vector3(0, 0, 1), 0x0000ff)
  return group
}

function createLinkLabelSprite(text, offset = new THREE.Vector3(0, 0, 0.01)) {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  canvas.width = 512; canvas.height = 128
  ctx.fillStyle = 'white'
  ctx.strokeStyle = 'black'
  ctx.font = 'bold 60px sans-serif'
  ctx.lineWidth = 6
  ctx.strokeText(text, 20, 80)
  ctx.fillText(text, 20, 80)
  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(0.3, 0.075, 1)
  sprite.position.copy(offset)
  sprite.renderOrder = 999
  return sprite
}

function addCoordinateHelpers(robot) {
  robot.traverse((child) => {
    if (child.type === 'URDFLink') {
      if (child.userData._coordAxes || child.userData._coordLabel) return
      const axes = createCustomAxes(0.15)
      child.add(axes)
      child.userData._coordAxes = axes
      const label = createLinkLabelSprite(child.name)
      child.add(label)
      child.userData._coordLabel = label
    }
  })
}

function removeCoordinateHelpers(robot) {
  robot?.traverse?.((child) => {
    if (child.userData?._coordAxes) { child.remove(child.userData._coordAxes); delete child.userData._coordAxes }
    if (child.userData?._coordLabel) { child.remove(child.userData._coordLabel); delete child.userData._coordLabel }
  })
}

function disposeObject(obj) {
  obj?.traverse?.((child) => {
    // 공유 리소스(__cacheRoot / __fromCacheClone)는 건너뛰기
    if (child.userData?.__cacheRoot || child.userData?.__fromCacheClone) return
    if (child.geometry) child.geometry.dispose?.()
    if (child.material) {
      const mats = Array.isArray(child.material) ? child.material : [child.material]
      mats.forEach((m) => {
        m.map?.dispose?.(); m.lightMap?.dispose?.(); m.aoMap?.dispose?.()
        m.emissiveMap?.dispose?.(); m.bumpMap?.dispose?.(); m.normalMap?.dispose?.()
        m.displacementMap?.dispose?.(); m.roughnessMap?.dispose?.(); m.metalnessMap?.dispose?.()
        m.alphaMap?.dispose?.(); m.envMap?.dispose?.(); m.dispose?.()
      })
    }
  })
}

/* ---------- controls ---------- */
function initControls() {
  const el = renderer.domElement
  controls = new OrbitControls(camera, el)
  controls.target.set(0, 0, 0.8)
  controls.enabled = enableOrbit.value
  controls.addEventListener('change', requestRender)
  controls.update()
}

/* ---------- joints ---------- */
function bakeJointMap(root) {
  urdfJointMap.clear()
  root?.traverse?.((child) => {
    if (child.type === 'URDFJoint' || child.isURDFJoint) {
      urdfJointMap.set(child.name, child)
    }
  })
}

function updateUrdfJoints() {
  if (!lastPose.value) return
  const q = lastPose.value
  const jointOrder = project.jointNames
  if (!jointOrder || jointOrder.length === 0) return

  for (let i = 0; i < jointOrder.length && i < q.length; i++) {
    const name = jointOrder[i]
    const joint = urdfJointMap.get(name)
    if (!joint) continue
    try { joint.setJointValue(q[i]) } catch { }
  }
}

/* ---------- tweakpane ---------- */
let pane = null
function initPane() {
  if (pane) return
  pane = new Pane({ container: paneContainer.value })
  const fView = pane.addFolder({ title: 'View', expanded: true })
  fView.addBinding(enableOrbit, 'value', { label: 'Orbit' })
  fView.addBinding(showCoordinates, 'value', { label: 'Coords' })
  fView.addBinding(gridSize, 'value', { label: 'Grid Size', min: 2, max: 20, step: 1 })
  fView.addBinding(gridDiv, 'value', { label: 'Grid Div', min: 1, max: 10, step: 1 })
  pane.on('change', (ev) => {
    if (ev.presetKey === 'value') { /* ignore */ }
    if (ev.target.label === 'Coords') {
      setShowCoordinates(showCoordinates.value)
      const robot = getModel()
      if (robot) {
        if (showCoordinates.value) addCoordinateHelpers(robot)
        else removeCoordinateHelpers(robot)
        requestRender()
      }
    }
    if (ev.target.label?.startsWith('Grid')) {
      if (gridMesh) {
        scene.remove(gridMesh)
        gridMesh.geometry.dispose?.()
        if (Array.isArray(gridMesh.material)) gridMesh.material.forEach(m => m.dispose?.())
        else gridMesh.material.dispose?.()
      }
      gridMesh = createGridPlane(gridSize.value, gridDiv.value)
      scene.add(gridMesh)
      requestRender()
    }
  })
}

/* ---------- lifecycle ---------- */
onMounted(async () => {
  await nextTick()
  const container = viewer.value
  const width = container.clientWidth
  const height = container.clientHeight

  if (motion) { }
  else {
    motion = new MotionClient(project.backendUrl + '/ws/motion')
    motion.connect()
  }

  // Scene
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x212121)

  // Camera
  camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100)
  camera.up.set(0, 0, 1)
  camera.position.set(2, 2, 2)
  camera.lookAt(0, 0, 0.8)

  // Renderer
  renderer = new THREE.WebGLRenderer({
    antialias: false,
    powerPreference: 'high-performance',
    precision: 'highp',
  })
  renderer.shadowMap.enabled = false
  renderer.setPixelRatio(1)
  renderer.setSize(width, height)
  container.appendChild(renderer.domElement)

  // Controls
  initControls()
  watch(enableOrbit, (enabled) => {
    if (controls) {
      controls.enabled = enabled
      controls.enableRotate = enabled
      requestRender()
    }
  })

  // Lights
  scene.add(new THREE.AmbientLight(0xdddddd, 0.4))
  const light = new THREE.DirectionalLight(0xffffff, 1)
  light.position.set(3, 3, 3)
  scene.add(light)

  // Grid
  gridMesh = createGridPlane(gridSize.value, gridDiv.value)
  scene.add(gridMesh)

  // Robot model
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

  const modelName = 'a'
  const modelVersion = 'v1.0'
  const urdfPath = modelVersion === 'v1.0'
    ? `/models/rby1${modelName}/urdf/model.urdf`
    : `/models/rby1${modelName}/urdf/model_${modelVersion}.urdf`

  if (isLoaded() && getModel()) {
    const robotModel = getModel()
    if (robotModel && !robotModel.userData.__cacheRoot) robotModel.userData.__cacheRoot = true
    scene.add(robotModel)
    if (getShowCoordinates()) addCoordinateHelpers(robotModel)
    bakeJointMap(robotModel)
  } else {
    loader.load(urdfPath, (urdf) => {
      urdf.userData.__cacheRoot = true
      setModel(urdf)
      setLoaded(true)
      scene.add(urdf)
      if (getShowCoordinates()) addCoordinateHelpers(urdf)
      bakeJointMap(urdf)
      requestRender()
    })
  }

  // Resize
  observer = new ResizeObserver(() => {
    const newW = container.clientWidth
    const newH = container.clientHeight
    camera.aspect = newW / newH
    camera.updateProjectionMatrix()
    renderer.setSize(newW, newH)
    requestRender()
  })
  observer.observe(container)

  // Tweakpane
  initPane()

  // 첫 렌더
  requestRender()

  // Motion WS events
  motion.onOpen(() => { motion.seek(0) })
  motion.onPose((_t, q) => {
    lastPose.value = q
    updateUrdfJoints()
    requestRender()
  })

  // 30Hz 업데이트 루프
  jointTimer = setInterval(() => {
    const now = performance.now()
    if (now - lastUpdateTime > UPDATE_INTERVAL) {
      updateUrdfJoints()
      lastUpdateTime = now
      requestRender()
    }
  }, UPDATE_INTERVAL)
})

onBeforeUnmount(() => {
  disposed = true
  if (jointTimer) clearInterval(jointTimer)
  if (observer && viewer.value) observer.unobserve(viewer.value)

  // 로봇 캐시 원본은 씬에서만 제거하고 dispose 금지
  try {
    const robotModel = getModel()
    if (robotModel) scene.remove(robotModel)
  } catch { }

  try { controls?.dispose?.() } catch { }
  try { renderer?.dispose?.() } catch { }

  // scene 내부 다른(비공유) 리소스만 정리
  try { disposeObject(scene) } catch { }
})
</script>

<style scoped>
.viewer-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
}

.viewer-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.viewer-container * {
  touch-action: auto !important;
}

.tweak-pane-container {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  width: 240px;
}
</style>
