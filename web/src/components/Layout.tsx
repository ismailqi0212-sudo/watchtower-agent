import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { AddStockDrawer } from './AddStockDrawer'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

export function Layout() {
  const [addOpen, setAddOpen] = useState(false)

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background text-foreground">
      <Sidebar onAdd={() => setAddOpen(true)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-hidden">
          <Outlet context={{ openAdd: () => setAddOpen(true) }} />
        </main>
      </div>
      <AddStockDrawer open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}
