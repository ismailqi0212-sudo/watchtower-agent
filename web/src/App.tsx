import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { WorkspaceProvider } from './lib/workspace'
import { DashboardPage } from './pages/DashboardPage'
import { EvalsPage } from './pages/EvalsPage'
import { ResearchPage } from './pages/ResearchPage'
import { RunPage } from './pages/RunPage'

function NotFound() {
  return (
    <div className="flex h-full items-center justify-center text-[12px] text-muted">
      页面不存在
    </div>
  )
}

export default function App() {
  return (
    <WorkspaceProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="runs/:runId" element={<RunPage />} />
          <Route path="research" element={<ResearchPage />} />
          <Route path="evals" element={<EvalsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </WorkspaceProvider>
  )
}
