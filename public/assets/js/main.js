import { createState } from './app/state.js';
import { computedConfig } from './app/computed.js';
import { methods } from './app/methods.js';
import { mountedHook } from './app/mounted.js';
import { hydrateAuth, setupAuthUi } from './config.js';

const { createApp } = window.Vue;

const app = createApp({
  data() {
    return createState();
  },
  computed: computedConfig,
  methods,
  mounted: mountedHook,
});

const appInstance = app.mount('#app');
window.app = appInstance;

setupAuthUi(appInstance);
hydrateAuth(appInstance);
