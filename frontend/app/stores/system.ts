import { defineStore } from 'pinia'
export const useSystemStore = defineStore('system', {
  state: () => ({
    robot: { ip: 'localhost:50051', connected: false, lastTs: 0 },
    quest: { ip: '192.168.0.50', connected: false, lastTs: 0 },
  })
})
