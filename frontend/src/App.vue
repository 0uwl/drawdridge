<script setup>
import { ref, onMounted } from 'vue'

// Placeholder root component — proves the dev-proxy/build-bake wiring works
// end to end. Real admin views (devices, users, log, settings) are a
// separate follow-up; see docs/frontend.md.
const status = ref('checking...')

onMounted(async () => {
  try {
    const res = await fetch('/health')
    const data = await res.json()
    status.value = data.status
  } catch {
    status.value = 'unreachable'
  }
})
</script>

<template>
  <main>
    <h1>Drawbridge</h1>
    <p>Backend status: {{ status }}</p>
  </main>
</template>
