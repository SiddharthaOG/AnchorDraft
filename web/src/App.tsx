import { HealthCheck } from './features/health/HealthCheck'

function App() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <HealthCheck />
      </div>
    </div>
  )
}

export default App