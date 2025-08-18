<!-- components/TransportBar.vue -->
<template>
  <div class="transport">
    <button class="btn" @click="store.stop()" title="Stop" aria-label="Stop">
      <!-- Material play/pause/stop와 동일한 path -->
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 6h12v12H6z" />
      </svg>
    </button>

    <button
      class="btn"
      v-if="!store.player.playing"
      @click="store.play()"
      title="Play"
      aria-label="Play"
    >
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 5v14l11-7z" />
      </svg>
    </button>

    <button
      class="btn"
      v-else
      @click="store.pause()"
      title="Pause"
      aria-label="Pause"
    >
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
      </svg>
    </button>

    <div class="time">{{ (store.player.t_ms / 1000).toFixed(2) }}s</div>
  </div>
</template>

<script setup lang="ts">
import { useProjectStore } from '@/stores/project'
const store = useProjectStore()
</script>

<style scoped>
.transport {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding-bottom: 8px;
  background: var(--bg-1);
  border: 0 solid var(--line-1);
  border-radius: 10px;
}
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--bg-2); color: var(--text-0);
  border: 1px solid var(--line-2); border-radius: 8px; padding: 6px 10px;
  font-size: 16px; cursor: pointer;
}
.btn:focus-visible { outline: 2px solid var(--line-2); outline-offset: 2px; }
.icon {
  width: 20px; height: 20px;
  fill: currentColor; /* 버튼의 글자색을 그대로 사용 */
}
.time { color: var(--text-1); padding-left: 8px; }
</style>
