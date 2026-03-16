import { ref, computed } from 'vue'
import { loginAPI, registerAPI } from '../api/auth'
import router from '../router'

const TOKEN_KEY = 'mirofish_token'
const USER_KEY = 'mirofish_user'
const TENANT_KEY = 'mirofish_tenant'

// Module-level refs — shared singleton state across all components
const user = ref(null)
const tenant = ref(null)

const isAuthenticated = computed(() => !!user.value && !!localStorage.getItem(TOKEN_KEY))

function loadFromStorage() {
  const storedUser = localStorage.getItem(USER_KEY)
  const storedTenant = localStorage.getItem(TENANT_KEY)
  if (storedUser) {
    try { user.value = JSON.parse(storedUser) } catch { user.value = null }
  }
  if (storedTenant) {
    try { tenant.value = JSON.parse(storedTenant) } catch { tenant.value = null }
  }
}

async function login(email, password) {
  const data = await loginAPI(email, password)
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY, JSON.stringify(data.user))
  localStorage.setItem(TENANT_KEY, JSON.stringify(data.tenant))
  user.value = data.user
  tenant.value = data.tenant
}

async function register(email, password, displayName, tenantName) {
  const data = await registerAPI(email, password, displayName, tenantName)
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY, JSON.stringify(data.user))
  localStorage.setItem(TENANT_KEY, JSON.stringify(data.tenant))
  user.value = data.user
  tenant.value = data.tenant
}

function logout() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(TENANT_KEY)
  user.value = null
  tenant.value = null
  router.push('/login')
}

export function useAuth() {
  return { user, tenant, isAuthenticated, login, register, logout, loadFromStorage }
}
