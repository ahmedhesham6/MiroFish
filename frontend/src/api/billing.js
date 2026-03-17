import api from './index'

export function getBillingStatus() {
  return api.get('/api/billing/status')
}

export function getCheckoutUrl(plan) {
  return api.post('/api/billing/checkout', { plan })
}
