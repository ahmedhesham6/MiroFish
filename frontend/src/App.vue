<template>
  <div>
    <nav v-if="showNav" class="app-nav">
      <div class="nav-brand">MIROFISH</div>
      <div class="nav-right">
        <span class="nav-user">{{ user?.email }}</span>
        <router-link to="/settings" class="nav-link">Settings</router-link>
        <button class="nav-logout" @click="logout">Logout</button>
      </div>
    </nav>
    <router-view />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuth } from './composables/useAuth'

const route = useRoute()
const { user, isAuthenticated, logout, loadFromStorage } = useAuth()

loadFromStorage()

const AUTH_ROUTES = ['/login', '/register']

const showNav = computed(() => {
  return isAuthenticated.value && !AUTH_ROUTES.includes(route.path)
})
</script>

<style>
/* Global style reset */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #000000;
  background-color: #ffffff;
}

/* Scrollbar styles */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: #000000;
}

::-webkit-scrollbar-thumb:hover {
  background: #333333;
}

/* Global button styles */
button {
  font-family: inherit;
}

/* App-level nav bar */
.app-nav {
  height: 48px;
  background: #000000;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-brand {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: #ffffff;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.nav-user {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #999999;
}

.nav-link {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #ffffff;
  text-decoration: none;
  letter-spacing: 0.05em;
}

.nav-link:hover {
  color: #FF4500;
}

.nav-logout {
  padding: 4px 12px;
  background: transparent;
  color: #ffffff;
  border: 1px solid #444444;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  letter-spacing: 0.05em;
}

.nav-logout:hover {
  border-color: #FF4500;
  color: #FF4500;
}
</style>
