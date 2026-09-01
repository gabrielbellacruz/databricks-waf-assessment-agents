/**
 * Entry point: mounts the app and registers the service worker.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { registerSW } from 'virtual:pwa-register';
import { App } from './App';
import { GlobalStyles } from './styles/GlobalStyles';

const container = document.getElementById('root');
if (!container) throw new Error('Root container #root not found');

createRoot(container).render(
  <StrictMode>
    <GlobalStyles />
    <App />
  </StrictMode>,
);

// Keeps the installed PWA up to date on the next visit
registerSW({ immediate: true });
