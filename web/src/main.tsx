/** Main application entry point. */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './features/auth/AuthProvider'
import { AppRouter } from './router'
import { AppErrorBoundary } from './components/AppErrorBoundary'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </AppErrorBoundary>
  </React.StrictMode>
)
