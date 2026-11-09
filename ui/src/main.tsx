import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { WeldCordonTool } from './WeldCordonTool.tsx'

const herramienta = window.location.hash.replace(/^#/, '') === 'cordon'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {herramienta ? <WeldCordonTool /> : <App />}
  </StrictMode>,
)
