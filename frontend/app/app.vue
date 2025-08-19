<template>
  <div class="app-shell">
    <Topbar />
    <Splitpanes>
      <!-- Left: Source + Inspector -->
      <Pane size="25" min-size="20">
        <Splitpanes horizontal>
          <Pane size="60">
            <SourcePanel />
          </Pane>
          <Pane size="40">
            <ClipBlendInspector v-if="selectedClip" />
            <div v-else class="empty-pane">클립을 선택하세요</div>
          </Pane>
        </Splitpanes>
      </Pane>

      <!-- Right -->
      <Pane size="75">
        <Splitpanes horizontal>
          <Pane size="70">
            <RobotView />
          </Pane>
          <Pane size="30">
            <TransportBar />
            <ClientOnly>
              <TimelineCanvas />
            </ClientOnly>
          </Pane>
        </Splitpanes>
      </Pane>
    </Splitpanes>
  </div>
</template>

<script setup>
import Topbar from '~/components/Topbar.vue'
import SourcePanel from '@/components/SourcePanel.vue'
import RobotView from '@/components/RobotView.vue'
import TransportBar from '@/components/TransportBar.vue'
import TimelineCanvas from '@/components/TimelineCanvas.vue'
import ClipBlendInspector from '@/components/ClipBlendInspector.vue'

import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'

import { storeToRefs } from 'pinia'
import { useProjectStore } from '@/stores/project'

// 선택 상태를 읽어서 Inspector 노출 제어
const project = useProjectStore()
const { selectedClip } = storeToRefs(project)


import { onMounted } from 'vue'

onMounted(() => {
  const dataURL = window.location.hostname
  const dataPort = 8001
  project.backendUrl = `http://${dataURL}:${dataPort}`;
})

</script>

<style scoped>
.empty-pane {
  opacity: 0.6;
  padding: 12px;
  font-size: small;
}
</style>
