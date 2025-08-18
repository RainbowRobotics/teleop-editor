let model = null
let loaded = false
let showCoordinates = false

export function useRobotCache() {
    return {
        getModel() {
            return model
        },
        setModel(m) {
            model = m
        },
        isLoaded() {
            return loaded
        },
        setLoaded(val) {
            loaded = val
        },
        getShowCoordinates() {
            return showCoordinates
        },
        setShowCoordinates(val) {
            showCoordinates = val
        }
    }
}