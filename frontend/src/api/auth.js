import api from './index'

export function loginAPI(email, password) {
  return api.post('/api/auth/login', { email, password })
}

export function registerAPI(email, password, displayName, tenantName) {
  return api.post('/api/auth/register', { email, password, display_name: displayName, tenant_name: tenantName })
}

export function getMeAPI() {
  return api.get('/api/auth/me')
}
