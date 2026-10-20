import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import AuthGate from './AuthGate'
import './style.css'

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <AuthGate />
  </StrictMode>,
)
