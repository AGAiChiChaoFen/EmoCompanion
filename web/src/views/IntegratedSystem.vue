<template>
  <div class="integrated-system">
    <ConversationPage :key="pageMode" :page-mode="pageMode" />
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import ConversationPage from '../components/ConversationPage.vue';

const route = useRoute();

const pageMode = computed(() => {
  return route.query.mode === 'chat' ? 'chat' : 'realtime';
});
</script>

<style scoped>
.integrated-system {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
