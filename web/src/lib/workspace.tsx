import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from './api'
import type { Health, Stock } from '../types'

interface WorkspaceValue {
  stocks: Stock[]
  health: Health | null
  loading: boolean
  refreshing: boolean
  error: string
  refresh: () => Promise<void>
  addStock: (symbol: string) => Promise<void>
  removeStock: (symbol: string) => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [stocks, setStocks] = useState<Stock[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setRefreshing(true)
    setError('')
    try {
      const [stockRes, healthRes] = await Promise.all([
        api.getStocks(),
        api.health(),
      ])
      setStocks(stockRes.items)
      setHealth(healthRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const addStock = useCallback(
    async (symbol: string) => {
      await api.addStock(symbol)
      await refresh()
    },
    [refresh],
  )

  const removeStock = useCallback(
    async (symbol: string) => {
      await api.deleteStock(symbol)
      await refresh()
    },
    [refresh],
  )

  const value = useMemo(
    () => ({
      stocks,
      health,
      loading,
      refreshing,
      error,
      refresh,
      addStock,
      removeStock,
    }),
    [stocks, health, loading, refreshing, error, refresh, addStock, removeStock],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext)
  if (!value) {
    throw new Error('useWorkspace must be used inside WorkspaceProvider')
  }
  return value
}
