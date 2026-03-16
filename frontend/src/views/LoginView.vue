<template>
  <div class="auth-container">
    <div class="auth-card">
      <div class="auth-brand">MIROFISH</div>
      <h1 class="auth-title">Sign In</h1>

      <form @submit.prevent="handleSubmit" class="auth-form">
        <div class="form-group">
          <label class="form-label">Email</label>
          <input
            v-model="email"
            type="email"
            class="form-input"
            placeholder="you@example.com"
            required
            autocomplete="email"
          />
        </div>

        <div class="form-group">
          <label class="form-label">Password</label>
          <input
            v-model="password"
            type="password"
            class="form-input"
            placeholder="••••••••"
            required
            autocomplete="current-password"
          />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          <span v-if="loading">Signing in...</span>
          <span v-else>Sign In →</span>
        </button>
      </form>

      <p class="auth-switch">
        Don't have an account?
        <router-link to="/register" class="auth-link">Register</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const { login } = useAuth()

const email = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleSubmit() {
  errorMsg.value = ''
  loading.value = true
  try {
    await login(email.value, password.value)
    router.push('/')
  } catch (err) {
    errorMsg.value = err?.response?.data?.error || err?.message || 'Login failed. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
:root {
  --black: #000000;
  --white: #ffffff;
  --orange: #FF4500;
  --gray-text: #666666;
  --border: #E5E5E5;
  --gray-light: #F5F5F5;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.auth-container {
  min-height: 100vh;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.auth-card {
  width: 100%;
  max-width: 400px;
  padding: 48px 40px;
  border: 1px solid #E5E5E5;
}

.auth-brand {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: #000000;
  margin-bottom: 32px;
}

.auth-title {
  font-size: 28px;
  font-weight: 700;
  color: #000000;
  margin-bottom: 32px;
  letter-spacing: -0.5px;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
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

.form-input {
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

.error-msg {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #FF4500;
  padding: 8px 12px;
  border: 1px solid #FF4500;
  background: rgba(255, 69, 0, 0.04);
}

.submit-btn {
  padding: 12px;
  background: #000000;
  color: #ffffff;
  border: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: background 0.15s;
  margin-top: 4px;
}

.submit-btn:hover:not(:disabled) {
  background: #FF4500;
}

.submit-btn:disabled {
  background: #999999;
  cursor: not-allowed;
}

.auth-switch {
  margin-top: 24px;
  font-size: 13px;
  color: #666666;
  text-align: center;
}

.auth-link {
  color: #000000;
  font-weight: 600;
  text-decoration: none;
}

.auth-link:hover {
  color: #FF4500;
}
</style>
