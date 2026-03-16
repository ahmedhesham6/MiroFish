<template>
  <div class="settings-container">
    <div class="settings-header">
      <div class="breadcrumb">
        <router-link to="/" class="breadcrumb-link">Home</router-link>
        <span class="breadcrumb-sep"> / </span>
        <span>Settings</span>
      </div>
      <h1 class="page-title">Settings</h1>
    </div>

    <div class="settings-body">
      <!-- User Info -->
      <section class="settings-section">
        <div class="section-label">Account</div>
        <div class="info-grid">
          <div class="info-row">
            <span class="info-key">Email</span>
            <span class="info-val">{{ user?.email || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-key">Display Name</span>
            <span class="info-val">{{ user?.displayName || user?.display_name || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-key">Role</span>
            <span class="info-val">{{ user?.role || 'member' }}</span>
          </div>
        </div>
      </section>

      <!-- Tenant Info -->
      <section class="settings-section">
        <div class="section-label">Organization</div>
        <div class="info-grid">
          <div class="info-row">
            <span class="info-key">Name</span>
            <span class="info-val">{{ tenant?.name || tenant?.tenantName || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-key">Plan</span>
            <span class="plan-badge">{{ tenant?.plan || 'free' }}</span>
          </div>
        </div>
      </section>

      <!-- Actions -->
      <section class="settings-section">
        <button class="logout-btn" @click="handleLogout">Logout</button>
      </section>
    </div>
  </div>
</template>

<script setup>
import { useAuth } from '../composables/useAuth'

const { user, tenant, logout } = useAuth()

function handleLogout() {
  logout()
}
</script>

<style scoped>
.settings-container {
  min-height: 100vh;
  background: #ffffff;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  color: #000000;
}

.settings-header {
  padding: 32px 48px 24px;
  border-bottom: 1px solid #E5E5E5;
}

.breadcrumb {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #666666;
  margin-bottom: 12px;
}

.breadcrumb-link {
  color: #666666;
  text-decoration: none;
}

.breadcrumb-link:hover {
  color: #FF4500;
}

.breadcrumb-sep {
  margin: 0 4px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.settings-body {
  max-width: 600px;
  padding: 40px 48px;
  display: flex;
  flex-direction: column;
  gap: 40px;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #999999;
  text-transform: uppercase;
  border-bottom: 1px solid #E5E5E5;
  padding-bottom: 8px;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
}

.info-key {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #666666;
  min-width: 120px;
  flex-shrink: 0;
}

.info-val {
  font-size: 14px;
  color: #000000;
  font-weight: 500;
}

.plan-badge {
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 8px;
  border: 1px solid #000000;
  color: #000000;
}

.logout-btn {
  padding: 10px 24px;
  background: transparent;
  color: #000000;
  border: 1px solid #000000;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  align-self: flex-start;
}

.logout-btn:hover {
  background: #000000;
  color: #ffffff;
}
</style>
