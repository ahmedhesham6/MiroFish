import api from './index'

export function getKeys() {
  return api.get('/api/settings/keys')
}

export function updateKeys(keys) {
  return api.put('/api/settings/keys', keys)
}
