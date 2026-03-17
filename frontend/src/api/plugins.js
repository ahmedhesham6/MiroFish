import api from './index'

export function listPlugins() {
  return api.get('/api/plugins')
}

export function getPlugin(name) {
  return api.get(`/api/plugins/${name}`)
}

export function enablePlugin(name) {
  return api.post(`/api/plugins/${name}/enable`)
}

export function disablePlugin(name) {
  return api.post(`/api/plugins/${name}/disable`)
}

export function getPluginConfig(name) {
  return api.get(`/api/plugins/${name}/config`)
}

export function updatePluginConfig(name, config) {
  return api.put(`/api/plugins/${name}/config`, config)
}

export function uploadPlugin(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/plugins/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
      ? (evt) => {
          if (evt.total) {
            onProgress(Math.round((evt.loaded * 100) / evt.total))
          }
        }
      : undefined
  })
}

export function deletePlugin(name) {
  return api.delete(`/api/plugins/${name}`)
}
