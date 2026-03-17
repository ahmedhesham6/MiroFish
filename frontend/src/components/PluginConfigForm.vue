<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title">Configure: {{ plugin.name }}</span>
        <button class="modal-close" @click="$emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <div v-if="loadError" class="field-error">{{ loadError }}</div>

        <div v-else-if="loading" class="config-loading">Loading config...</div>

        <form v-else @submit.prevent="handleSave" class="config-form">
          <div v-if="fields.length === 0" class="no-fields">
            This plugin has no configurable fields.
          </div>

          <div v-for="field in fields" :key="field.key" class="form-group">
            <label class="form-label">
              {{ field.label }}
              <span v-if="field.required" class="required-mark">*</span>
            </label>
            <p v-if="field.description" class="field-desc">{{ field.description }}</p>

            <!-- Boolean -->
            <label v-if="field.type === 'boolean'" class="checkbox-label">
              <input type="checkbox" v-model="formValues[field.key]" class="checkbox-input" />
              <span>{{ formValues[field.key] ? 'Enabled' : 'Disabled' }}</span>
            </label>

            <!-- Enum (select) -->
            <select
              v-else-if="field.type === 'enum'"
              v-model="formValues[field.key]"
              class="form-input"
            >
              <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
            </select>

            <!-- Integer -->
            <input
              v-else-if="field.type === 'integer'"
              type="number"
              step="1"
              v-model.number="formValues[field.key]"
              class="form-input"
              :placeholder="field.placeholder || ''"
            />

            <!-- Number -->
            <input
              v-else-if="field.type === 'number'"
              type="number"
              v-model.number="formValues[field.key]"
              class="form-input"
              :placeholder="field.placeholder || ''"
            />

            <!-- String (default) -->
            <input
              v-else
              type="text"
              v-model="formValues[field.key]"
              class="form-input"
              :placeholder="field.placeholder || ''"
            />

            <p v-if="fieldErrors[field.key]" class="field-error-inline">{{ fieldErrors[field.key] }}</p>
          </div>

          <div v-if="saveError" class="field-error">{{ saveError }}</div>
          <div v-if="saveSuccess" class="field-success">Config saved.</div>

          <div class="form-actions">
            <button type="button" class="cancel-btn" @click="$emit('close')">Cancel</button>
            <button type="submit" class="save-btn" :disabled="savePending">
              <span v-if="savePending">Saving...</span>
              <span v-else>Save Config</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getPluginConfig, updatePluginConfig } from '../api/plugins'

const props = defineProps({
  plugin: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'saved'])

const loading = ref(true)
const loadError = ref('')
const savePending = ref(false)
const saveError = ref('')
const saveSuccess = ref(false)

const fields = ref([])
const formValues = reactive({})
const fieldErrors = reactive({})

function buildFields(schema) {
  if (!schema || !schema.properties) return []
  const required = new Set(schema.required || [])
  return Object.entries(schema.properties).map(([key, def]) => {
    let type = 'string'
    if (def.type === 'boolean') type = 'boolean'
    else if (def.type === 'integer') type = 'integer'
    else if (def.type === 'number') type = 'number'
    else if (def.enum) type = 'enum'

    return {
      key,
      label: def.title || key,
      description: def.description || '',
      type,
      options: def.enum || [],
      placeholder: def.examples?.[0] ? String(def.examples[0]) : '',
      required: required.has(key),
      default: def.default !== undefined ? def.default : null
    }
  })
}

function initFormValues(fieldList, existingConfig) {
  for (const field of fieldList) {
    if (existingConfig && existingConfig[field.key] !== undefined) {
      formValues[field.key] = existingConfig[field.key]
    } else if (field.default !== null) {
      formValues[field.key] = field.default
    } else if (field.type === 'boolean') {
      formValues[field.key] = false
    } else if (field.type === 'integer' || field.type === 'number') {
      formValues[field.key] = ''
    } else {
      formValues[field.key] = ''
    }
  }
}

function validate() {
  let valid = true
  for (const key of Object.keys(fieldErrors)) {
    delete fieldErrors[key]
  }
  for (const field of fields.value) {
    if (field.required) {
      const val = formValues[field.key]
      if (val === '' || val === null || val === undefined) {
        fieldErrors[field.key] = `${field.label} is required.`
        valid = false
      }
    }
  }
  return valid
}

async function handleSave() {
  if (!validate()) return
  saveError.value = ''
  saveSuccess.value = false
  savePending.value = true
  try {
    const config = {}
    for (const field of fields.value) {
      const val = formValues[field.key]
      if (val !== '' && val !== null && val !== undefined) {
        config[field.key] = val
      }
    }
    await updatePluginConfig(props.plugin.name, config)
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
    emit('saved', props.plugin.name)
  } catch (err) {
    saveError.value = err?.response?.data?.error || err?.message || 'Save failed.'
  } finally {
    savePending.value = false
  }
}

onMounted(async () => {
  loading.value = true
  loadError.value = ''
  try {
    const data = await getPluginConfig(props.plugin.name)
    const schema = props.plugin.config_schema || {}
    fields.value = buildFields(schema)
    initFormValues(fields.value, data?.data || {})
  } catch (err) {
    loadError.value = err?.response?.data?.error || err?.message || 'Failed to load config.'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #ffffff;
  width: 100%;
  max-width: 520px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  border: 1px solid #000000;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #E5E5E5;
}

.modal-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #000000;
}

.modal-close {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  color: #666666;
  padding: 4px;
  line-height: 1;
}

.modal-close:hover {
  color: #000000;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.config-loading {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #999999;
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.no-fields {
  font-size: 13px;
  color: #666666;
  padding: 12px 0;
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

.required-mark {
  color: #FF4500;
  margin-left: 2px;
}

.field-desc {
  font-size: 12px;
  color: #999999;
  margin: 0;
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
  width: 100%;
  box-sizing: border-box;
}

.form-input:focus {
  border-color: #000000;
}

.form-input::placeholder {
  color: #cccccc;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #000000;
  cursor: pointer;
}

.checkbox-input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.field-error-inline {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #FF4500;
  margin: 0;
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

.form-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.cancel-btn {
  padding: 10px 20px;
  background: transparent;
  color: #000000;
  border: 1px solid #E5E5E5;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.cancel-btn:hover {
  background: #F5F5F5;
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
}

.save-btn:hover:not(:disabled) {
  background: #FF4500;
}

.save-btn:disabled {
  background: #999999;
  cursor: not-allowed;
}
</style>
