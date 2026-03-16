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
      <!-- Account -->
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

      <!-- Organization / Plan -->
      <section class="settings-section">
        <div class="section-label">Organization</div>
        <div class="info-grid">
          <div class="info-row">
            <span class="info-key">Name</span>
            <span class="info-val">{{ tenant?.name || tenant?.tenantName || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-key">Plan</span>
            <span :class="['plan-badge', planClass]">{{ currentPlan }}</span>
          </div>
          <template v-if="billingStatus">
            <div class="info-row">
              <span class="info-key">Projects</span>
              <span class="info-val">{{ billingStatus.projectsUsed ?? '—' }} / {{ billingStatus.projectsLimit ?? '∞' }}</span>
            </div>
            <div class="info-row">
              <span class="info-key">Simulations</span>
              <span class="info-val">{{ billingStatus.simulationsUsed ?? '—' }} / {{ billingStatus.simulationsLimit ?? '∞' }}</span>
            </div>
          </template>
        </div>

        <div v-if="!isPro" class="upgrade-row">
          <p class="upgrade-hint">Upgrade to Pro for unlimited usage and custom API keys.</p>
          <button class="upgrade-btn" @click="handleUpgrade" :disabled="checkoutLoading">
            <span v-if="checkoutLoading">Loading...</span>
            <span v-else>Upgrade to Pro →</span>
          </button>
          <p v-if="checkoutError" class="field-error">{{ checkoutError }}</p>
        </div>
      </section>

      <!-- API Keys (BYOK) -->
      <section class="settings-section">
        <div class="section-label">API Keys (BYOK)</div>

        <template v-if="isPro">
          <p class="section-desc">Override global API keys with your own. Leave blank to use defaults.</p>

          <div v-if="keysLoading" class="keys-loading">Loading keys...</div>

          <form v-else @submit.prevent="handleSaveKeys" class="keys-form">
            <div class="form-group">
              <label class="form-label">LLM API Key</label>
              <div class="input-with-toggle">
                <input
                  v-model="form.llm_api_key"
                  :type="reveal.llm_api_key ? 'text' : 'password'"
                  class="form-input"
                  placeholder="sk-..."
                  autocomplete="off"
                />
                <button type="button" class="reveal-btn" @click="reveal.llm_api_key = !reveal.llm_api_key">
                  {{ reveal.llm_api_key ? 'Hide' : 'Show' }}
                </button>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">LLM Base URL</label>
              <input
                v-model="form.llm_base_url"
                type="text"
                class="form-input"
                placeholder="https://api.openai.com/v1"
                autocomplete="off"
              />
            </div>

            <div class="form-group">
              <label class="form-label">LLM Model Name</label>
              <input
                v-model="form.llm_model_name"
                type="text"
                class="form-input"
                placeholder="gpt-4o"
                autocomplete="off"
              />
            </div>

            <div class="form-group">
              <label class="form-label">Zep API Key</label>
              <div class="input-with-toggle">
                <input
                  v-model="form.zep_api_key"
                  :type="reveal.zep_api_key ? 'text' : 'password'"
                  class="form-input"
                  placeholder="z_..."
                  autocomplete="off"
                />
                <button type="button" class="reveal-btn" @click="reveal.zep_api_key = !reveal.zep_api_key">
                  {{ reveal.zep_api_key ? 'Hide' : 'Show' }}
                </button>
              </div>
            </div>

            <div v-if="saveError" class="field-error">{{ saveError }}</div>
            <div v-if="saveSuccess" class="field-success">Keys saved.</div>

            <button type="submit" class="save-btn" :disabled="savePending">
              <span v-if="savePending">Saving...</span>
              <span v-else>Save Keys</span>
            </button>
          </form>
        </template>

        <template v-else>
          <div class="keys-disabled">
            <p class="keys-disabled-msg">API Keys are available on Pro and Enterprise plans.</p>
            <button class="upgrade-btn" @click="handleUpgrade" :disabled="checkoutLoading">
              <span v-if="checkoutLoading">Loading...</span>
              <span v-else>Upgrade to Pro →</span>
            </button>
          </div>
        </template>
      </section>

      <!-- Logout -->
      <section class="settings-section">
        <button class="logout-btn" @click="logout">Logout</button>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useAuth } from '../composables/useAuth'
import { getKeys, updateKeys } from '../api/settings'
import { getBillingStatus, getCheckoutUrl } from '../api/billing'

const { user, tenant, logout } = useAuth()

const billingStatus = ref(null)
const checkoutLoading = ref(false)
const checkoutError = ref('')

const keysLoading = ref(false)
const savePending = ref(false)
const saveError = ref('')
const saveSuccess = ref(false)

const form = reactive({
  llm_api_key: '',
  llm_base_url: '',
  llm_model_name: '',
  zep_api_key: ''
})

const reveal = reactive({
  llm_api_key: false,
  zep_api_key: false
})

const currentPlan = computed(() => {
  return billingStatus.value?.plan || tenant.value?.plan || 'free'
})

const isPro = computed(() => {
  const plan = currentPlan.value.toLowerCase()
  return plan === 'pro' || plan === 'enterprise'
})

const planClass = computed(() => {
  const plan = currentPlan.value.toLowerCase()
  if (plan === 'pro') return 'plan-pro'
  if (plan === 'enterprise') return 'plan-enterprise'
  return 'plan-free'
})

async function loadBilling() {
  try {
    const data = await getBillingStatus()
    billingStatus.value = data
  } catch {
    // Billing endpoint may not be available yet
  }
}

async function loadKeys() {
  if (!isPro.value) return
  keysLoading.value = true
  try {
    const data = await getKeys()
    form.llm_api_key = data.llm_api_key || ''
    form.llm_base_url = data.llm_base_url || ''
    form.llm_model_name = data.llm_model_name || ''
    form.zep_api_key = data.zep_api_key || ''
  } catch {
    // Keys endpoint may not exist yet
  } finally {
    keysLoading.value = false
  }
}

async function handleSaveKeys() {
  saveError.value = ''
  saveSuccess.value = false
  savePending.value = true
  try {
    await updateKeys({
      llm_api_key: form.llm_api_key || null,
      llm_base_url: form.llm_base_url || null,
      llm_model_name: form.llm_model_name || null,
      zep_api_key: form.zep_api_key || null
    })
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (err) {
    saveError.value = err?.response?.data?.error || err?.message || 'Save failed.'
  } finally {
    savePending.value = false
  }
}

async function handleUpgrade() {
  checkoutError.value = ''
  checkoutLoading.value = true
  try {
    const data = await getCheckoutUrl('pro')
    if (data.url) {
      window.open(data.url, '_blank')
    }
  } catch (err) {
    checkoutError.value = err?.response?.data?.error || err?.message || 'Could not start checkout.'
  } finally {
    checkoutLoading.value = false
  }
}

onMounted(async () => {
  await loadBilling()
  await loadKeys()
})
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

.section-desc {
  font-size: 13px;
  color: #666666;
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
}

.plan-free {
  border: 1px solid #cccccc;
  color: #666666;
}

.plan-pro {
  border: 1px solid #FF4500;
  color: #FF4500;
}

.plan-enterprise {
  border: 1px solid #000000;
  background: #000000;
  color: #ffffff;
}

.upgrade-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border: 1px solid #E5E5E5;
  background: #F5F5F5;
}

.upgrade-hint {
  font-size: 13px;
  color: #666666;
}

.upgrade-btn {
  padding: 10px 20px;
  background: #FF4500;
  color: #ffffff;
  border: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  align-self: flex-start;
}

.upgrade-btn:hover:not(:disabled) {
  background: #cc3700;
}

.upgrade-btn:disabled {
  background: #999999;
  cursor: not-allowed;
}

.keys-loading {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #999999;
}

.keys-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: #666666;
  text-transform: uppercase;
}

.input-with-toggle {
  display: flex;
}

.form-input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #E5E5E5;
  background: #ffffff;
  color: #000000;
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: #000000;
}

.form-input::placeholder {
  color: #cccccc;
}

.reveal-btn {
  padding: 0 12px;
  background: #F5F5F5;
  color: #666666;
  border: 1px solid #E5E5E5;
  border-left: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.reveal-btn:hover {
  background: #E5E5E5;
  color: #000000;
}

.field-error {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #FF4500;
  padding: 8px 12px;
  border: 1px solid #FF4500;
  background: rgba(255, 69, 0, 0.04);
}

.field-success {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #008000;
  padding: 8px 12px;
  border: 1px solid #008000;
  background: rgba(0, 128, 0, 0.04);
}

.save-btn {
  padding: 10px 24px;
  background: #000000;
  color: #ffffff;
  border: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  align-self: flex-start;
}

.save-btn:hover:not(:disabled) {
  background: #FF4500;
}

.save-btn:disabled {
  background: #999999;
  cursor: not-allowed;
}

.keys-disabled {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid #E5E5E5;
  background: #F5F5F5;
}

.keys-disabled-msg {
  font-size: 13px;
  color: #666666;
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
