// Preload for the error screen only. It fills in the message and wires the two buttons;
// no API is exposed to the page at all.
import { ipcRenderer } from 'electron';

window.addEventListener('DOMContentLoaded', () => {
  const message =
    new URLSearchParams(location.search).get('message') ?? 'The application could not start.';
  const target = document.getElementById('details');
  if (target) target.textContent = message;
  document
    .getElementById('restart')
    ?.addEventListener('click', () => void ipcRenderer.invoke('shell:restart'));
  document
    .getElementById('quit')
    ?.addEventListener('click', () => void ipcRenderer.invoke('shell:quit'));
});
